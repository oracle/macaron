# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
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

from macaron.repo_finder import repo_finder_deps_dev
from macaron.repo_finder.repo_finder import to_domain_from_known_purl_types
from macaron.slsa_analyzer.git_service import GIT_SERVICES

logger: logging.Logger = logging.getLogger(__name__)

# An optional named capture group "prefix" that accepts one of the following:
# - A string of any characters starting with an alphabetic character, ending with one of:
#   - One non-alphanumeric character, one alphabetic character, and one or more numbers.
#   - One number and one alphabetic character.
#   - Two alphabetic characters.
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
# PREFIX_START + <artifact_name> + PREFIX_END
PREFIX_START = "(?P<prefix_0>(?:(?:[a-z].*(?:[a-z0-9][a-z][0-9]+|[0-9][a-z]|[a-z]{2}))|[a-z]{2})|"
PREFIX_END = ")?"

# An alternative prefix pattern that is intended for a single use case: A prefix that contains a part that is
# difficult to distinguish from part of a version, i.e. java-v1-1.1.0 (prefix: java-v1, version: 1.1.0)
PREFIX_WITH_SEPARATOR = "(?P<prefix_1>(?:[a-z].*(?P<prefix_sep_1>[^a-z0-9])[a-z][0-9]+))(?:(?P=prefix_sep_1))"

# An optional named capture group "prefix_sep" that accepts one of:
# - A 'v', 'r', or 'c' character that is not preceded by a non-alphanumeric character.
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
PREFIX_SEPARATOR = "(?P<prefix_sep_0>(?:(?:(?<![0-9a-z])[vrc])|(?:[^0-9a-z][vrc])|[^0-9a-z])(?:[^0-9a-z])?)?"

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
SUFFIX_SEPARATOR = "(?P<suffix_sep>(?:[^0-9a-z]{1,2}(?:(?=[^0-9])|(?!.))))?"

# The suffix optionally accepts:
# A string that starts with an alphabetic character, and continues for one or more characters of any kind.
SUFFIX = "(?P<suffix>[a-z].*)?"

# If a version string has less parts than this number it will be padded with additional zeros to provide better matching
# opportunities.
# For this to be applied, the version string must not have any non-numeric parts.
# E.g 1.2 (2) -> 1.2.0.0 (4), 1.2.RELEASE (3) -> 1.2.RELEASE (3), 1.DEV-5 (3) -> 1.DEV-5 (3)
MAX_ZERO_DIGIT_EXTENSION = 4

split_pattern = re.compile("[^0-9a-z]", flags=re.IGNORECASE)
validation_pattern = re.compile("^[0-9a-z]+$", flags=re.IGNORECASE)
alphabetic_only_pattern = re.compile("^[a-z]+$", flags=re.IGNORECASE)
hex_only_pattern = re.compile("^[0-9a-f]+$", flags=re.IGNORECASE)
numeric_only_pattern = re.compile("^[0-9]+$")
versioned_string = re.compile("^([a-z]+)(0*)([1-9]+[0-9]*)$", flags=re.IGNORECASE)  # e.g. RC1, M5, etc.


class AbstractPurlType(Enum):
    """The type represented by a PURL in terms of repositories versus artifacts.

    Unsupported types are allowed as a third type.
    """

    REPOSITORY = (0,)
    ARTIFACT = (1,)
    UNSUPPORTED = (2,)


def find_commit(git_obj: Git, purl: PackageURL) -> str | None:
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
    str | None
        The digest, or None if the commit cannot be correctly retrieved.
    """
    version = purl.version
    if not version:
        logger.debug("Missing version for analysis target: %s", purl.name)
        return None

    repo_type = determine_abstract_purl_type(purl)
    if repo_type == AbstractPurlType.REPOSITORY:
        return extract_commit_from_version(git_obj, version)
    if repo_type == AbstractPurlType.ARTIFACT:
        return find_commit_from_version_and_name(git_obj, purl.name, version)
    logger.debug("Type of PURL is not supported for commit finding: %s", purl.type)
    return None


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


def extract_commit_from_version(git_obj: Git, version: str) -> str | None:
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
    str | None
        The digest, or None if the commit cannot be correctly retrieved.
    """
    # A commit hash is 40 characters in length, but commits are often referenced using only some of those.
    commit: Commit | None = None
    if 7 <= len(version) <= 40 and re.match(hex_only_pattern, version):
        try:
            commit = git_obj.get_commit(version)
        except BadName as error:
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
        return None

    return commit.hash if commit else None


def find_commit_from_version_and_name(git_obj: Git, name: str, version: str) -> str | None:
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
    str | None
        The digest, or None if the commit cannot be correctly retrieved.
    """
    logger.debug("Searching for commit of artifact version using tags: %s@%s", name, version)

    # Only consider tags that have a commit.
    valid_tags = {}
    for tag in git_obj.repo.tags:
        commit = _get_tag_commit(tag)
        if not commit:
            logger.debug("No commit found for tag: %s", tag)
            continue

        tag_name = str(tag)
        valid_tags[tag_name] = tag

    if not valid_tags:
        logger.debug("No tags with commits found for %s", name)
        return None

    # Match tags.
    matched_tags = match_tags(list(valid_tags.keys()), name, version)

    if not matched_tags:
        logger.debug("No tags matched for %s", name)
        return None

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
        return None

    logger.debug(
        "Found tag %s with commit %s for artifact version %s@%s",
        tag,
        hexsha,
        name,
        version,
    )
    return hexsha if hexsha else None


def _build_version_pattern(name: str, version: str) -> tuple[Pattern | None, list[str]]:
    """Build a version pattern to match the passed version string.

    Parameters
    ----------
    name: str
        The name string.
    version: str
        The version string.

    Returns
    -------
    tuple[Pattern | None, list[str]]
        The tuple of the regex pattern that will match the version, and the list of version parts that were extracted.
        If an exception occurs from any regex operation, the pattern will be returned as None.

    """
    if not version:
        return None, []

    name = re.escape(name)

    # The version is split on non-alphanumeric characters to separate the version parts from the non-version parts.
    # e.g. 1.2.3-DEV -> [1, 2, 3, DEV]
    split = split_pattern.split(version)
    logger.debug("Split version: %s", split)

    parts = []
    for part in split:
        # Validate the split part by checking it is only comprised of alphanumeric characters.
        valid = validation_pattern.match(part)
        if not valid:
            continue
        parts.append(part)

    if not parts:
        logger.debug("Version contained no valid parts: %s", version)
        return None, []

    this_version_pattern = ""
    has_non_numeric_suffix = False
    # Detect versions that end with a zero, so the zero can be made optional.
    has_trailing_zero = len(split) > 2 and split[-1] == "0"
    for count, part in enumerate(parts):
        numeric_only = numeric_only_pattern.match(part)

        if not has_non_numeric_suffix and not numeric_only:
            # A non-numeric part enables the flag for treating this and all remaining parts as version suffix parts.
            # Within the built regex, such parts will be made optional.
            # E.g.
            # - 1.2.RELEASE -> 'RELEASE' becomes optional.
            # - 3.1.test.2 -> 'test' and '2' become optional.
            has_non_numeric_suffix = True

        # This part will be made optional in the regex if it matches the correct requirements:
        # - There is more than one version part, e.g. 1.2 (2), 1.2.3 (3)
        # - AND either of:
        #   - This is the last version part and it has a trailing zero, e.g. 10
        #   - OR has_non_numeric_suffix is True (See its comments above for more details)
        optional = len(split) > 1 and ((count == len(split) - 1 and has_trailing_zero) or has_non_numeric_suffix)

        if optional:
            this_version_pattern = this_version_pattern + "("

        if count == 1:
            this_version_pattern = this_version_pattern + INFIX_1
        elif count > 1:
            this_version_pattern = this_version_pattern + INFIX_3

        # Add the current part to the pattern.
        this_version_pattern = this_version_pattern + part

        if optional:
            # Complete the optional capture group.
            this_version_pattern = this_version_pattern + ")?"

    # If the version parts are less than MAX_ZERO_DIGIT_EXTENSION, add additional optional zeros to pad out the
    # regex, and thereby provide an opportunity to map mismatches between version and tags (that are still the same
    # number).
    # E.g. MAX_ZERO_DIGIT_EXTENSION = 4 -> 1.2 to 1.2.0.0, or 3 to 3.0.0.0, etc.
    if not has_non_numeric_suffix and 0 < len(parts) < MAX_ZERO_DIGIT_EXTENSION:
        for count in range(len(parts), MAX_ZERO_DIGIT_EXTENSION):
            # Additional zeros added for this purpose make use of a back reference to the first matched separator.
            this_version_pattern = this_version_pattern + "(" + (INFIX_2 if count > 1 else INFIX_1) + "0)?"

    this_version_pattern = (
        f"^(?:(?:{PREFIX_WITH_SEPARATOR})|(?:{PREFIX_START}{name}{PREFIX_END}{PREFIX_SEPARATOR}))(?P<version>"
        f"{this_version_pattern}){SUFFIX_SEPARATOR}{SUFFIX}$"
    )
    try:
        return re.compile(this_version_pattern, flags=re.IGNORECASE), parts
    except Exception as error:  # pylint: disable=broad-exception-caught
        # The regex library uses an internal error that cannot be used here to satisfy pylint.
        logger.debug("Error while compiling version regex: %s", error)
        return None, []


def match_tags(tag_list: list[str], name: str, version: str) -> list[str]:
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
    list[str]
        The list of tags that matched the pattern.
    """
    # Create the pattern for the passed version.
    pattern, parts = _build_version_pattern(name, version)
    if not pattern:
        return []

    # Match the tags.
    matched_tags = []
    for tag in tag_list:
        match = pattern.match(tag)
        if not match:
            continue
        # Tags are append with their match information for possible further evaluation.
        matched_tags.append(
            {
                "tag": tag,
                "version": match.group("version"),
                "prefix": match.group("prefix_0") or match.group("prefix_1"),
                "prefix_sep": match.group("prefix_sep_0") or match.group("prefix_sep_1"),
                "suffix_sep": match.group("suffix_sep"),
                "suffix": match.group("suffix"),
            }
        )

    if len(matched_tags) <= 1:
        return [_["tag"] for _ in matched_tags]

    # In the case of multiple matches, further work must be done.

    # If any of the matches contain a prefix that matches the target artifact name, and otherwise perfectly matches
    # the version, remove those that don't.
    named_tags = []
    for item in matched_tags:
        prefix: str | None = item["prefix"]
        if not prefix:
            continue
        if "/" in prefix:
            # Exclude prefix parts that exists before a forward slash, e.g. rel/
            _, _, prefix = prefix.rpartition("/")
        if (
            prefix.lower() == name.lower()
            and _compute_tag_version_similarity(item["version"], item["suffix"], parts) == 0
        ):
            named_tags.append(item)

    if named_tags:
        matched_tags = named_tags

    # If multiple tags still remain, sort them based on the closest match in terms of individual parts.
    if len(matched_tags) > 1:
        matched_tags.sort(
            key=lambda matched_tag: _compute_tag_version_similarity(
                matched_tag["version"], matched_tag["suffix"], parts
            )
        )

    return [_["tag"] for _ in matched_tags]


def _compute_tag_version_similarity(tag_version: str, tag_suffix: str, version_parts: list[str]) -> int:
    """Return a sort value based on how well the tag version and tag suffix match the parts of the actual version.

    Parameters
    ----------
    tag_version: str
        The tag's version.
    tag_suffix: str
        The tag's suffix.
    version_parts: str
        The version parts from the version string.

    Returns
    -------
    int
        The sort value based on the similarity between the tag and version, lower means more similar.

    """
    count = len(version_parts)
    # Reduce count for each direct match between version parts and tag version.
    tag_version_text = tag_version.lower()
    for part in version_parts:
        part = part.lower()
        if part in tag_version_text:
            tag_version_text = tag_version_text.replace(part, "", 1)
            count = count - 1

    # Try to reduce the count further based on the tag suffix.
    if tag_suffix:
        last_part = version_parts[-1].lower()
        # The tag suffix might consist of multiple version parts, e.g. RC1.RELEASE
        suffix_split = split_pattern.split(tag_suffix)
        # Try to match suffix parts to version.
        versioned_string_match = False
        if len(suffix_split) > 1:
            for suffix_part in suffix_split:
                suffix_part = suffix_part.lower()
                if alphabetic_only_pattern.match(suffix_part) and suffix_part == last_part:
                    # If the suffix part only contains alphabetic characters, reduce the count if it
                    # matches the version.
                    count = count - 1
                    continue

                variable_suffix_pattern = _create_suffix_tag_comparison_pattern(suffix_part)
                if not variable_suffix_pattern:
                    continue

                if versioned_string_match:
                    count = count + 1
                    continue

                # If the suffix part contains alphabetic characters followed by numeric characters,
                # reduce the count if it closely matches the version (once only), otherwise increase the count.
                if re.match(variable_suffix_pattern, last_part):
                    count = count - 1
                    versioned_string_match = True
                else:
                    count = count + 1

        variable_suffix_pattern = _create_suffix_tag_comparison_pattern(tag_suffix)
        if variable_suffix_pattern:
            if re.match(variable_suffix_pattern, last_part):
                count = count - 1
            else:
                count = count + 1
        else:
            count = count + 1

    return count


def _create_suffix_tag_comparison_pattern(tag_part: str) -> str | None:
    """Create pattern to compare part of a tag with part of a version.

    The created pattern allows for numeric parts within the tag to have a variable number of zeros for matching.
    """
    versioned_string_result = versioned_string.match(tag_part)
    if not versioned_string_result:
        return None

    variable_suffix_pattern = f"{versioned_string_result.group(1)}"
    if not versioned_string_result.group(2):
        return f"{variable_suffix_pattern}{versioned_string_result.group(3)}"

    return f"{variable_suffix_pattern}(0*){versioned_string_result.group(3)}"


def _get_tag_commit(tag: TagReference) -> Commit | None:
    """Return the commit of the passed tag.

    This is a standalone function to more clearly handle the potential error raised by accessing the tag's commit
    property.
    """
    try:
        return tag.commit
    except ValueError:
        return None
