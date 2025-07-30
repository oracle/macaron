# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic for matching PackageURL versions to repository commits via the tags they contain."""
import logging
import re
from enum import Enum
from re import Pattern

from git import TagReference
from gitdb.exc import BadName
from packageurl import PackageURL
from pydriller import Commit, Git

from macaron.repo_finder import repo_finder_deps_dev, to_domain_from_known_purl_types
from macaron.repo_finder.repo_finder_enums import CommitFinderInfo
from macaron.slsa_analyzer.git_service import GIT_SERVICES

logger: logging.Logger = logging.getLogger(__name__)

# An optional named capture group "prefix" that accepts one of the following:
# - A string of any characters that ends with one of:
#   - One non-alphanumeric character, one alphabetic character, and one or more numbers.
#   - One number and one alphabetic character.
#   - Two alphabetic characters.
#   - One or two numbers.
# - OR
# - Two alphabetic characters.
# E.g.
# - 'name_prefix'     of 'name_prefix_1.2.3'
# - 'prefix-a444'     of 'prefix-a444-v3.2.1.0'
# - 'vm'              of 'vm-5-5-5'
# - 'name-prefix-j5u' of 'name-prefix-j5u//r0_0_1'
# This part of the pattern terminates with an OR character to allow for it to be combined with the name of the target
# artifact as another possible prefix match.
# E.g.
# PREFIX_START + <artifact_name> + PREFIX_END.
PREFIX_START = "(?P<prefix_0>(?:(?:.*(?:[a-z0-9][a-z][0-9]+|[0-9][a-z]|[a-z]{2}|[0-9]{1,2}))|[a-z]{2})|"
PREFIX_END = ")?"

# An alternative prefix pattern that is intended for a single use case: A prefix that contains a part that is
# difficult to distinguish from part of a version, i.e. java-v1-1.1.0 (prefix: java-v1, version: 1.1.0).
PREFIX_WITH_SEPARATOR = "(?P<prefix_1>(?:[a-z].*(?P<prefix_sep_1>[^a-z0-9])[a-z][0-9]+))(?:(?P=prefix_sep_1))"

# Another alternative prefix pattern that accepts a string of any number of alphabetic characters and no separator.
PREFIX_WITHOUT_SEPARATOR = "(?P<prefix_2>(?:[a-z]+))"

# An named capture group "prefix_sep" that accepts one of:
# - A 'v', 'r', or 'c' character that is not preceded by a non-alphanumeric character (negative look behind).
# ('c' is probably a typo as it was found in only one example tag, but accepting any single alphabetic character
# would also most likely be fine.)
# - A non-alphanumeric character followed by 'v', 'r', or 'c'.
# - A non-alphanumeric character.
# Then optionally ending with one non-alphanumeric character.
# E.g.
# - '_v-' of 'prefix_v-1.2.3'
# - 'r_'  of 'r_3_3_3'
# - 'c'   of 'c4.1'
# - '.'   of 'name.9-9-9-9'
PREFIX_SEPARATOR = "(?P<prefix_sep_0>(?:(?:(?<![0-9a-z])[vrc])|(?:[^0-9a-z][vrc])|[^0-9a-z])(?:[^0-9a-z])?)"

# Together, the prefix and prefix separator exist to separate the prefix from version part of a tag, while ensuring that
# the prefix is free from non-prefix characters (the separator). Note that the prefix is expected to be at least two
# characters in length to prevent overlap with separators and confusion with versions; the prefix separator is at most
# three characters; and a negative lookback passes if there are no preceding characters.

# The infix accepts either:
# - One to three alphabetic characters.
# - One to three non-alphanumeric characters.
# Note: The upper limit of three could be reduced to two based on current data.
INFIX_3 = "([a-z]{1,3}|[^0-9a-z]{1,3})"
INFIX_1 = f"(?P<sep>{INFIX_3})"  # A named capture group of INFIX_3.
INFIX_2 = "(?P=sep)"  # A back reference to INFIX_1.

# The infix exists between parts of the version string. The most recent design resulted in use of a back reference to
# ensure non-suffix version parts were separated by the same separator, e.g. 1.2.3 but not 1.2-3. However, one edge
# case required this to be partially reverted, requiring 1.2-3 to be accepted, while another edge case where
# additional zeros need to be added after a version to pad its length, e.g. 1.2 becomes 1.2.0.0, still requires it.

# The suffix separator exists for much the same purpose as the prefix separator: splitting the suffix into the actual
# suffix, and the characters that join it to the version.
# It optionally accepts:
# One to two non-alphanumeric characters that are followed by either:
# - A non-numeric character (positive lookahead).
# - No character of any kind (negative lookahead).
# E.g.
# - '_'  of 'prefix_1.2.3_suffix'
# - '..  of 'name-v-4-4-4..RELEASE'
# - '#'  of 'v0.0.1#'
SUFFIX_SEPARATOR = "(?P<suffix_sep>(?:[^0-9a-z]{1,2}(?:(?=[^0-9])|(?!.))))"

# The suffix optionally accepts:
# A string that starts with an alphanumeric character, and continues for one or more characters of any kind.
SUFFIX = "(?P<suffix>[a-z0-9].*)?"

# If a version string has less parts than this number it will be padded with additional zeros to provide better matching
# opportunities.
# For this to be applied, the version string must not have any non-numeric parts.
# E.g 1.2 (2) -> 1.2.0.0 (4), 1.2.RELEASE (3) -> 1.2.RELEASE (3), 1.DEV-5 (3) -> 1.DEV-5 (3).
MAX_ZERO_DIGIT_EXTENSION = 4

split_pattern = re.compile("[^0-9a-z]", flags=re.IGNORECASE)  # Used to split version strings.
anti_split_pattern = re.compile("[0-9a-z]+", flags=re.IGNORECASE)  # Inversion of split_pattern.
validation_pattern = re.compile("^[0-9a-z]+$", flags=re.IGNORECASE)  # Used to verify characters in version parts.
alphabetic_only_pattern = re.compile("^[a-z]+$", flags=re.IGNORECASE)
hex_only_pattern = re.compile("^[0-9a-f]+$", flags=re.IGNORECASE)
numeric_only_pattern = re.compile("^[0-9]+$")
special_suffix_pattern = re.compile("^([0-9]+)([a-z]+[0-9]+)$", flags=re.IGNORECASE)  # E.g. 1.10rc1.
versioned_string = re.compile("^([a-z]*)(0*)([1-9]+[0-9]*)?$", flags=re.IGNORECASE)  # E.g. RC1, 15, 0010, M, etc.
multiple_zero_pattern = re.compile("^0+$")
name_version_pattern = re.compile("([0-9]+(?:[.][0-9]+)*)")  # Identifies version-like parts within prefixes.


class AbstractPurlType(Enum):
    """The type represented by a PURL in terms of repositories versus artifacts.

    Unsupported types are allowed as a third type.
    """

    REPOSITORY = (0,)
    ARTIFACT = (1,)
    UNSUPPORTED = (2,)


def find_commit(git_obj: Git, purl: PackageURL) -> tuple[str | None, CommitFinderInfo]:
    """Try to find the commit matching the passed PURL.

    The PURL may be a repository type, e.g. GitHub, in which case the commit might be in its version part.
    Otherwise, the PURL should be a package manager type, e.g. Maven, in which case the commit must be found from
    the artifact version.

    Parameters
    ----------
    git_obj: Git
        The repository.
    purl: PackageURL
        The PURL of the analysis target.

    Returns
    -------
    tuple[str | None, CommitFinderInfo]
        The digest, or None if the commit cannot be correctly retrieved, and the outcome to report.
    """
    version = purl.version
    if not version:
        logger.debug("Missing version for analysis target: %s", purl.name)
        return None, CommitFinderInfo.NO_VERSION_PROVIDED

    repo_type = determine_abstract_purl_type(purl)
    if repo_type == AbstractPurlType.REPOSITORY:
        return extract_commit_from_version(git_obj, version)
    if repo_type == AbstractPurlType.ARTIFACT:
        return find_commit_from_version_and_name(git_obj, purl.name, version)
    logger.debug("Type of PURL is not supported for commit finding: %s", purl.type)
    return None, CommitFinderInfo.UNSUPPORTED_PURL_TYPE


def determine_abstract_purl_type(purl: PackageURL) -> AbstractPurlType:
    """Determine if the passed purl is a repository type, artifact type, or unsupported type.

    Parameters
    ----------
    purl: PackageURL
        A PURL that represents a repository, artifact, or something that is not supported.

    Returns
    -------
    PurlType
        The identified type of the PURL.
    """
    available_domains = [git_service.hostname for git_service in GIT_SERVICES if git_service.hostname]
    domain = to_domain_from_known_purl_types(purl.type) or (purl.type if purl.type in available_domains else None)
    if domain:
        # PURL is a repository type.
        return AbstractPurlType.REPOSITORY
    try:
        repo_finder_deps_dev.DepsDevType(purl.type)
        # PURL is an artifact type.
        return AbstractPurlType.ARTIFACT
    except ValueError:
        # PURL is an unsupported type.
        return AbstractPurlType.UNSUPPORTED


def extract_commit_from_version(git_obj: Git, version: str) -> tuple[str | None, CommitFinderInfo]:
    """Try to extract the commit from the PURL's version parameter.

    E.g.
    With commit: pkg:github/package-url/purl-spec@244fd47e07d1004f0aed9c.
    With tag: pkg:github/apache/maven@maven-3.9.1.

    Parameters
    ----------
    git_obj: Git
        The repository.
    version: str
        The version part from the analysis target's PURL.

    Returns
    -------
    tuple[str | None, CommitFinderInfo]
        The digest, or None if the commit cannot be correctly retrieved, and the outcome to report.
    """
    # A commit hash is 40 characters in length, but commits are often referenced using only some of those.
    commit: Commit | None = None
    if 7 <= len(version) <= 40 and re.match(hex_only_pattern, version):
        try:
            commit = git_obj.get_commit(version)
        except (BadName, ValueError) as error:
            logger.debug("Failed to retrieve commit: %s", error)

    if not commit:
        # Treat the 'commit' as a tag.
        try:
            commit = git_obj.get_commit_from_tag(version)
        except (IndexError, ValueError) as error:
            # If the tag exists but represents a tree or blob, a ValueError will be raised when trying to retrieve its
            # commit.
            logger.debug("Failed to retrieve commit: %s", error)

    if not commit:
        return None, CommitFinderInfo.REPO_PURL_FAILURE

    return commit.hash if commit else None, CommitFinderInfo.MATCHED


def find_commit_from_version_and_name(git_obj: Git, name: str, version: str) -> tuple[str | None, CommitFinderInfo]:
    """Try to find the matching commit in a repository of a given version (and name) via tags.

    The passed version is used to match with the tags in the target repository. The passed name is used in cases where
    a repository makes use of named prefixes in its tags.

    Parameters
    ----------
    git_obj: Git
        The repository.
    name: str
        The name of the analysis target.
    version: str
        The version of the analysis target.

    Returns
    -------
    tuple[str | None, CommitFinderInfo]
        The digest, or None if the commit cannot be correctly retrieved, and the outcome to report.
    """
    logger.debug("Searching for commit of artifact version using tags: %s@%s", name, version)

    # Only consider tags that have a commit.
    repo_tags = git_obj.repo.tags
    if not repo_tags:
        logger.debug("No tags found for %s", name)
        return None, CommitFinderInfo.NO_TAGS

    valid_tags = {}
    for tag in repo_tags:
        commit = _get_tag_commit(tag)
        if not commit:
            logger.debug("No commit found for tag: %s", tag)
            continue

        tag_name = str(tag)
        valid_tags[tag_name] = tag

    if not valid_tags:
        logger.debug("No tags with commits found for %s", name)
        return None, CommitFinderInfo.NO_TAGS_WITH_COMMITS

    # Match tags.
    matched_tags, outcome = match_tags(list(valid_tags.keys()), name, version)

    if not matched_tags:
        logger.debug("No tags matched for %s", name)
        return None, outcome

    if len(matched_tags) > 1:
        logger.debug("Tags found for %s: %s", name, len(matched_tags))
        logger.debug("Best match: %s", matched_tags[0])
        logger.debug("Up to 5 others: %s", matched_tags[1:6])

    tag_name = matched_tags[0]
    tag = valid_tags[tag_name]
    if not tag:
        # Tag names are taken from valid_tags and should always exist within it.
        logger.debug("Missing tag name from tag dict: %s not in %s", tag_name, valid_tags.keys())

    try:
        hexsha = tag.commit.hexsha
    except ValueError:
        logger.debug("Error trying to retrieve digest of commit: %s", tag.commit)
        return None, CommitFinderInfo.NO_TAG_COMMIT

    logger.debug(
        "Found tag %s with commit %s for artifact version %s@%s",
        tag,
        hexsha,
        name,
        version,
    )
    return hexsha if hexsha else None, CommitFinderInfo.MATCHED


def _split_name(name: str) -> list[str]:
    """Split an artifact name, or prefix that might be an artifact name, into its delimited components."""
    result = []
    # Find all version-like parts.
    number_match = name_version_pattern.findall(name)
    if number_match:
        for match in number_match:
            result.append(match)
            name = name.replace(match, "")

    # Split remainder on delimiters.
    name_split = split_pattern.split(name)
    for item in name_split:
        if not item.strip():
            continue
        result.append(item)

    return result


def _split_version(version: str) -> tuple[list[str], bool, set[int]]:
    """Split a version into its constituent parts, and flag if the version contained more than one kind of seperator."""
    # The version is split on non-alphanumeric characters to separate the version parts from the non-version parts.
    # E.g. 1.2.3-DEV -> [1, 2, 3, DEV].
    split = split_pattern.split(version)
    version_separators = _split_separators(version)
    multi_sep = False
    if len(set(version_separators)) != 1:
        multi_sep = True

    parts = []
    special_index = set()
    for index, part in enumerate(split):
        # Validate the split part by checking it is only comprised of alphanumeric characters.
        valid = validation_pattern.match(part)
        if not valid:
            continue
        special_suffix = special_suffix_pattern.match(part)
        if special_suffix:
            # Special case: a release candidate suffix with no suffix separator.
            parts.append(special_suffix.group(1))
            parts.append(special_suffix.group(2))
            special_index.add(index + 1)
        else:
            parts.append(part)

    return parts, multi_sep, special_index


def _split_separators(version: str) -> list[str]:
    """Split a string on its separators and return only those."""
    split = anti_split_pattern.split(version)
    return [item for item in split if item]


def _build_version_pattern(name: str, version: str) -> tuple[Pattern | None, list[str], CommitFinderInfo]:
    """Build a version pattern to match the passed version string.

    Parameters
    ----------
    name: str
        The name string.
    version: str
        The version string.

    Returns
    -------
    tuple[Pattern | None, list[str], CommitFinderInfo]
        The tuple of the regex pattern that will match the version, the list of version parts that were extracted, and
        the outcome to report. If an exception occurs from any regex operation, the pattern will be returned as None.

    """
    if not version:
        return None, [], CommitFinderInfo.NO_VERSION_PROVIDED

    # Escape input to prevent it being treated as regex.
    name = re.escape(name)

    parts, multi_sep, special_indices = _split_version(version)

    if not parts:
        logger.debug("Version contained no valid parts: %s", version)
        return None, [], CommitFinderInfo.INVALID_VERSION

    logger.debug("Version parts: %s", parts)

    # Determine optional suffixes.
    optional_start_index = determine_optional_suffix_index(version, parts)

    # Detect versions that end with a zero number (0, 00, 000, etc.), so that part can be made optional.
    has_trailing_zero = len(parts) > 2 and multiple_zero_pattern.match(parts[-1])

    # Create the pattern.
    this_version_pattern = ""
    for count, part in enumerate(parts):
        # This part will be made optional in the regex if it is within the optional suffix range, or is the final part
        # and is a trailing zero.
        optional = (optional_start_index and count >= optional_start_index) or (
            count == len(parts) - 1 and has_trailing_zero
        )

        if optional:
            this_version_pattern = this_version_pattern + "("

        if count == 1:
            this_version_pattern = this_version_pattern + INFIX_1
        elif count > 1:
            if multi_sep:
                # Allow for a change in separator type.
                this_version_pattern = this_version_pattern + INFIX_3
            else:
                # Expect the same separator as matched by INFIX_1.
                this_version_pattern = this_version_pattern + INFIX_2

        if count in special_indices:
            # If this part exists because it was split from its original part, flag the separator as optional.
            # E.g. 4rc7 -> 4, rc7 (with optional separator between 4 and rc7).
            this_version_pattern = this_version_pattern + "?"

        if numeric_only_pattern.match(part) and not optional_start_index:
            # Allow for any number of preceding zeros when the part is numeric only. E.g. 000 + 1, 0 + 20.
            this_version_pattern = this_version_pattern + "0*"

        # Add the current part to the pattern.
        if count == 0:
            # Add a negative look behind that prevents the first part from being matched inside a multi-digit number.
            # E.g. '11.33' will not match '1.33'.
            this_version_pattern = this_version_pattern + "(?<![0-9])"
        this_version_pattern = this_version_pattern + part

        if optional:
            # Complete the optional capture group.
            this_version_pattern = this_version_pattern + ")?"

    # If the version parts are less than MAX_ZERO_DIGIT_EXTENSION, add additional optional zeros to pad out the
    # regex, and thereby provide an opportunity to map mismatches between version and tags (that are still the same
    # number).
    # E.g. MAX_ZERO_DIGIT_EXTENSION = 4 -> 1.2 to 1.2.0.0, or 3 to 3.0.0.0, etc.
    if not optional_start_index and 0 < len(parts) < MAX_ZERO_DIGIT_EXTENSION:
        for count in range(len(parts), MAX_ZERO_DIGIT_EXTENSION):
            # Additional zeros added for this purpose make use of a back reference to the first matched separator.
            this_version_pattern = this_version_pattern + "(" + (INFIX_2 if count > 1 else INFIX_1) + "0)?"

    # Combine the version pattern with the pre-defined pattern parts.
    this_version_pattern = (
        f"^(?:(?:{PREFIX_WITH_SEPARATOR})|(?:{PREFIX_WITHOUT_SEPARATOR})|"
        f"(?:{PREFIX_START}{name}{PREFIX_END}{PREFIX_SEPARATOR}))?(?P<version>"
        f"{this_version_pattern})(?:{SUFFIX_SEPARATOR}{SUFFIX})?$"
    )

    # Compile the pattern.
    try:
        return re.compile(this_version_pattern, flags=re.IGNORECASE), parts, CommitFinderInfo.MATCHED
    except Exception as error:  # pylint: disable=broad-exception-caught
        # The regex library uses an internal error that cannot be used here to satisfy pylint.
        logger.debug("Error while compiling version regex: %s", error)
        return None, [], CommitFinderInfo.REGEX_COMPILE_FAILURE


def determine_optional_suffix_index(version: str, parts: list[str]) -> int | None:
    """Determine optional suffix index of a given version string.

    Version parts that are alphanumeric, and do not come before parts that are purely numeric, can be treated
    as optional suffixes.
    E.g.
    - 1.2.RELEASE -> 'RELEASE' becomes optional.
    - 3.1.test.2.M5 -> 'M5' becomes optional.
    Parts that come after a change in seperator are also flagged as optional.
    - 2.2-3 -> '3' becomes optional.

    Parameters
    ----------
    version: str
        The version string of the software component.
    parts: list[str]
        The non-separator parts of the version produced by a prior split operation.

    Returns
    -------
    int | None
        The index of the first optional part, or None if not found. This is a zero-based index to match the parts
        parameter, with the caveat that a value of zero cannot be returned due to the behaviour of the algorithm.
        In other words, there must always be at least one non-optional part.
    """
    optional_start_index = None
    separators = _split_separators(version)
    last_separator = separators[0] if separators else None
    for index in range(1, len(parts)):
        # Check if current part should be optional, or reset the index if not.
        optional_start_index = None if numeric_only_pattern.match(parts[index]) else index

        if not last_separator:
            continue

        if index >= len(separators):
            continue

        # Check if parts should be made optional based on a difference in separators.
        new_separator = separators[index]
        if new_separator != last_separator:
            optional_start_index = index + 1
            break
        last_separator = new_separator

    return optional_start_index


def match_tags(tag_list: list[str], name: str, version: str) -> tuple[list[str], CommitFinderInfo]:
    """Return items of the passed tag list that match the passed artifact name and version.

    Parameters
    ----------
    tag_list: list[str]
        The list of tags to check.
    name: str
        The name of the analysis target.
    version: str
        The version of the analysis target.

    Returns
    -------
    tuple[list[str], CommitFinderInfo]
        The list of tags that matched the pattern, if any, and the outcome to report.
    """
    logger.debug("Tag Sample: %s", tag_list[:5])

    # If any tag exactly matches the version, return it immediately.
    # Also allow for an optional 'v' prefix, and tags of the form: <release_prefix>/<artifact_name>-<version>.
    # Generally version identifiers do not contain the `v` prefix, while tags often do. If a version does contain such
    # a prefix, it is expected to be in the tag also. If not, the `v` prefix is left as optional.
    v_prefix = "(?:v)?" if not version.lower().startswith("v") else ""
    almost_exact_pattern = re.compile(
        f"^(?:[^/]+/)?(?P<prefix>{re.escape(name)}-)?{v_prefix}{re.escape(version)}$", re.IGNORECASE
    )

    # Compare tags to the almost exact pattern. Prefer tags that matched the name prefix as well.
    almost_exact_matches = {}
    last_match = None
    prefix_match = None
    for tag in tag_list:
        match = almost_exact_pattern.match(tag)
        if match:
            almost_exact_matches[tag] = match
            last_match = tag
            if match.group(1):
                prefix_match = tag
    if prefix_match:
        return [prefix_match], CommitFinderInfo.MATCHED
    if last_match:
        return [last_match], CommitFinderInfo.MATCHED

    # Create the more complicated pattern for the passed version.
    pattern, parts, outcome = _build_version_pattern(name, version)
    if not pattern:
        return [], outcome

    # Match the tags.
    matched_tags = []
    for tag in tag_list:
        match = pattern.match(tag)
        if not match:
            continue
        # Tags are appended with their match information for possible further evaluation.
        matched_tag: dict[str, str] = {
            "tag": tag,
            "version": match.group("version"),
            "prefix": match.group("prefix_0") or match.group("prefix_1") or match.group("prefix_2"),
            "prefix_sep": match.group("prefix_sep_0") or match.group("prefix_sep_1"),
            "suffix_sep": match.group("suffix_sep"),
            "suffix": match.group("suffix"),
        }
        matched_tags.append(matched_tag)

    matched_tags = _fix_misaligned_tag_matches(matched_tags, version)

    if not matched_tags:
        logger.debug("Failed to match any tags.")
        return [], CommitFinderInfo.NO_TAGS_MATCHED

    if len(matched_tags) == 1:
        return [_["tag"] for _ in matched_tags], CommitFinderInfo.MATCHED

    # In the case of multiple matches, further work must be done.

    # If any of the matches contain a prefix that matches the target artifact name, and otherwise perfectly matches
    # the version, remove those that don't.
    named_tags = []
    for item in matched_tags:
        prefix = item["prefix"]
        if not prefix:
            continue
        if "/" in prefix:
            # Exclude prefix parts that exists before a forward slash, e.g. rel/.
            _, _, prefix = prefix.rpartition("/")
        if (
            prefix.lower() == name.lower()
            and _compute_tag_version_similarity(
                "", "", item["version"], item["suffix"], item["suffix_sep"], parts, version, name
            )
            == 0
        ):
            named_tags.append(item)

    if named_tags:
        matched_tags = named_tags

    # If multiple tags still remain, sort them based on the closest match in terms of individual parts.
    if len(matched_tags) > 1:
        matched_tags.sort(
            key=lambda matched_tag_: _compute_tag_version_similarity(
                matched_tag_["prefix"],
                matched_tag_["prefix_sep"],
                matched_tag_["version"],
                matched_tag_["suffix"],
                matched_tag_["suffix_sep"],
                parts,
                version,
                name,
            )
        )

    return [_["tag"] for _ in matched_tags], CommitFinderInfo.MATCHED


def _fix_misaligned_tag_matches(matched_tags: list[dict[str, str]], version: str) -> list[dict[str, str]]:
    """Fix tags that were matched due to alignment errors in the prefix.

    E.g. v6.3.1 -> Prefix 'v6', version '3.1' could match Version '3.1.0'.
    """
    if not matched_tags:
        return matched_tags

    filtered_tags = []
    for matched_tag in matched_tags:
        prefix = matched_tag["prefix"]
        prefix_sep = matched_tag["prefix_sep"]
        if not version:
            # Reject matches with no version part.
            continue

        if not prefix:
            # Matches without a prefix cannot be evaluated here.
            filtered_tags.append(matched_tag)
            continue

        # Get the separators for the actual version, and the parts and separators for the matched tag's prefix.
        version_seps = _split_separators(version)
        version_sep = version_seps[0] if version_seps else ""
        prefixes, _, _ = _split_version(prefix)
        prefix_separators = _split_separators(prefix)

        # Try to move any version-like strings from the end of the prefix to the version.
        # E.g. An optional 'v', 'r', or 'c', followed by one or more numbers.
        # TODO consider cases where multiple version-like parts exist in the prefix.
        #  E.g. Prefix: 'prefix-1.2' Version: '3.4' from Artifact Version 'prefix-1.2.3.4'.
        if re.match("^([vrc])?[0-9]+$", prefixes[-1], re.IGNORECASE):
            if version_sep and version_sep == prefix_sep:
                # Ensure there is a version separator and a prefix separator, and they match.
                # E.g. '.' from '1.2' and '.' from '<rest-of-prefix>.v4'.
                new_prefix = ""
                # Create the new prefix.
                for index in range(len(prefixes) - 1):
                    if index > 0:
                        new_prefix = new_prefix + prefix_separators[index - 1]
                    new_prefix = new_prefix + prefixes[index]

                # Get the parts for the actual version.
                version_parts, _, _ = _split_version(version)
                if version_parts[0] not in prefixes[-1]:
                    # Only perform the fix if the prefix version-like parts match (contain) parts of the sought version.
                    continue

                # Create the new matched_tag version.
                tag_version = matched_tag["version"]
                new_version = prefixes[-1] + version_sep + tag_version

                # Check if the new version can match the actual version.
                bad_match = False
                new_parts, _, _ = _split_version(new_version)
                for index in range(min(len(new_parts), len(version_parts))):
                    if version_parts[index] not in new_parts[index]:
                        bad_match = True
                        break
                if bad_match:
                    # The match is rejected.
                    continue

                # Apply change to match.
                matched_tag["prefix"] = new_prefix
                matched_tag["version"] = new_version

        filtered_tags.append(matched_tag)

    return filtered_tags


def _compute_tag_version_similarity(
    prefix: str,
    prefix_sep: str,
    tag_version: str,
    tag_suffix: str,
    tag_suffix_sep: str,
    version_parts: list[str],
    version: str,
    artifact_name: str,
) -> float:
    """Return a sort value based on how well the tag version and tag suffix match the parts of the actual version.

    Parameters
    ----------
    prefix: str
        The tag's prefix.
    prefix_sep: str
        The prefix separator.
    tag_version: str
        The tag's version.
    tag_suffix: str
        The tag's suffix.
    tag_suffix_sep: str
        The tag's suffix seperator.
    version_parts: str
        The version parts from the version string.
    version: str
        The actual version being sought.
    artifact_name: str
        The name of the artifact.

    Returns
    -------
    float
        The sort value based on the similarity between the tag and version, lower means more similar.

    """
    tag_version_text = tag_version.lower()
    tag_parts, _, _ = _split_version(tag_version_text)
    if tag_suffix:
        tag_suffix = tag_suffix.lower()
    if tag_suffix and len(tag_parts) < len(version_parts):
        # Append the tag suffix parts to the list of the tag parts if the version has more parts.
        suffix_parts, _, _ = _split_version(tag_suffix.lower())
        for suffix_part in suffix_parts:
            tag_parts.append(suffix_part)

    # Start the count as the highest length of the version parts and tag parts lists.
    part_count = max(len(version_parts), len(tag_parts))

    # Reduce count for each direct match between version parts and tag version.
    for index in range(part_count):
        if index >= len(version_parts) or index >= len(tag_parts):
            continue
        part = version_parts[index].lower()
        if part in tag_parts[index]:
            part_count = part_count - 1

    score: float = part_count

    # A set of release related words to notice during evaluation.
    release_set = {"rel", "release", "fin", "final"}

    # Try to reduce the score further based on the tag suffix.
    if tag_suffix:
        last_part = version_parts[-1].lower()
        # The tag suffix might consist of multiple version parts, e.g. RC1.RELEASE.
        suffix_split, _, _ = _split_version(tag_suffix)
        # Try to match suffix parts to version.
        versioned_string_match = False
        if len(suffix_split) > 1:
            # Multiple suffix parts.
            for suffix_part in suffix_split:
                suffix_part = suffix_part.lower()
                if alphabetic_only_pattern.match(suffix_part) and suffix_part == last_part:
                    # If the suffix part only contains alphabetic characters, reduce the score if it
                    # matches the version.
                    score = score - 1
                    continue

                # Create a pattern to allow loose matching between the tag part and version.
                variable_suffix_pattern = _create_suffix_tag_comparison_pattern(suffix_part)
                if not variable_suffix_pattern:
                    # If no pattern could be created the tag part worsens the score of this match.
                    score = score + 1
                    continue

                if versioned_string_match:
                    # If a comparison already matched, worsen the score for this superfluous tag part.
                    score = score + 1
                    continue

                # If the suffix part contains alphabetic characters followed by numeric characters,
                # reduce the score if it closely matches the version (once only), otherwise increase the score.
                if re.match(variable_suffix_pattern, last_part):
                    score = score - 1
                    versioned_string_match = True
                else:
                    score = score + 1
        else:
            # Single suffix part.
            if len(tag_parts) < len(version_parts):
                # When there are fewer tag parts than version parts the 'last' version part must take that into account.
                last_part_index = len(version_parts) - len(tag_parts) + 1
                last_part = version_parts[-last_part_index]
            if tag_suffix != last_part:
                variable_suffix_pattern = _create_suffix_tag_comparison_pattern(tag_suffix)
                if variable_suffix_pattern:
                    if re.match(variable_suffix_pattern, last_part):
                        # A half value is used here as otherwise it can lead to the same score as a tag_suffix that is
                        # equal to the last part.
                        score = score - 0.5
                    elif tag_suffix not in release_set:
                        # The suffix does not match, and is not similar.
                        score = score + 1
                    else:
                        score = score + 0.2
                else:
                    # If no suffix pattern can be created the suffix cannot be matched to the last version part.
                    score = score + 1
            else:
                # Decrease score if there is a single suffix, and it matches the last version part.
                score = score - 0.5

    score = 0 if score < 0 else score

    if tag_suffix:
        # Slightly prefer matches with a release related suffix.
        suffix_parts, _, _ = _split_version(tag_suffix)
        for suffix_part in suffix_parts:
            if suffix_part in version_parts:
                continue
            if suffix_part in release_set:
                score = score - 0.1

    if prefix:
        pre_score = score
        if len(prefix) > 2:
            # Prefer tags whose prefix is a superstring of the artifact name, or release related.
            name_split = _split_name(artifact_name.lower())
            name_set = set(name_split)
            prefix_split = _split_name(prefix.lower())
            bonus = 0.0
            for prefix_part in prefix_split:
                if prefix_part in name_set:
                    # Matches accumulate bonus score.
                    bonus = bonus - 0.1
                else:
                    if prefix_part.lower() in release_set:
                        # If the prefix part is release related, improve the score directly.
                        score = score - 0.11
                        continue
                    # A non-match sets the bonus to a penalty.
                    bonus = 0.11
                    if name_version_pattern.match(prefix_part):
                        # Heavily penalise non-matching version-like values.
                        bonus = 1.0
                    # Do not check remaining parts after a non-match.
                    break
            score = score + bonus

        if pre_score == score:
            # Prefer tags with shorter prefixes. Only applies if no other change was made for the prefix already.
            if len(prefix) == 1 and alphabetic_only_pattern.match(prefix):
                # Prefer 'v' over alternatives.
                if prefix.lower() != "v":
                    score = score + 0.01
            else:
                # Worsen the score based on the length of the prefix.
                score = score + min(len(prefix) / 100, 0.09)

    if len(version_parts) > 1 > score:
        # Prefer tags with version separators that exist in the version string.
        tag_separators = _split_separators(tag_version)
        for tag_separator in tag_separators:
            if tag_separator not in version:
                score = score + 0.5
                break

        if tag_suffix and tag_suffix in version_parts:
            # If the tag has a suffix, and it is part of the version, ensure the seperator matches exactly.
            suffix_index = version_parts.index(tag_suffix)
            version_separators = _split_separators(version)
            if suffix_index - 1 < len(version_separators):
                if version_separators[suffix_index - 1] != tag_suffix_sep:
                    score = score + 0.5

    if prefix_sep:
        # Prefer shorter prefix separators.
        prefix_sep_len = len(prefix_sep)
        if "v" in prefix_sep:
            # Ignore the 'v' prefix separator.
            prefix_sep_len = prefix_sep_len - 1
        # The regex patterns ensure this length is never greater than 3.
        score = score + prefix_sep_len * 0.01

    return score


def _create_suffix_tag_comparison_pattern(tag_part: str) -> Pattern | None:
    """Create pattern to compare part of a tag with part of a version.

    The created pattern allows for numeric parts within the tag to have a variable number of zeros for matching.
    """
    # The tag part must be a number that may optionally start with one or more alphabet characters.
    versioned_string_result = versioned_string.match(tag_part)
    if not versioned_string_result:
        return None

    # Combine the alphabetic and zero-extended numeric parts.
    return re.compile(f"{versioned_string_result.group(1)}(0*){versioned_string_result.group(3)}", re.IGNORECASE)


def _get_tag_commit(tag: TagReference) -> Commit | None:
    """Return the commit of the passed tag.

    This is a standalone function to more clearly handle the potential error raised by accessing the tag's commit
    property.
    """
    try:
        return tag.commit
    except ValueError:
        return None
