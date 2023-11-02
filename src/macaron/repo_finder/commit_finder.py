# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic for matching PackageURL versions to repository commits via the tags they contain."""
import logging
import re
from re import Pattern

from git import TagReference
from packageurl import PackageURL
from pydriller import Git

logger: logging.Logger = logging.getLogger(__name__)

# An optional named capture group "prefix" that accepts one of the following:
# - A string of any characters starting with an alphabetic character, ending with one of:
#   - One alphabetic character and one or more numbers.
#   - One number and one alphabetic character.
#   - Two alphabetic characters.
# - OR
# - Two alphabetic characters.
# E.g.
# - name_prefix
# - prefix-a444
# - vm
# - name-prefix-j5u
PREFIX = "^(?P<prefix>(?:[a-z].*(?:[a-z][0-9]+|[0-9][a-z]|[a-z]{2}))|[a-z]{2})?"

# An optional named capture group "prefix_sep" that accepts one of:
# - A 'v', 'r', or 'c' character that is not preceded by a non-alphanumeric character.
# ('c' is probably a typo as it was found in only one example tag, but accepting any single alphabetic character
# would also most likely be fine.)
# - A non-alphanumeric character followed by 'v', 'r', or 'c'.
# - A non-alphanumeric character.
# Then optionally ending with one non-alphanumeric character.
# E.g.
# - _v-
# - r_
# - c
# - .
PREFIX_SEPARATOR = "(?P<prefix_sep>(?:(?:(?<![0-9a-z])[vrc])|(?:[^0-9a-z][vrc])|[^0-9a-z])(?:[^0-9a-z])?)?"

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
# One to two non-alphanumeric characters that are followed by a non-numeric character (positive lookahead).
SUFFIX_SEPARATOR = "(?P<suffix_sep>[^0-9a-z]{1,2}(?=[^0-9]))?"

# The suffix optionally accepts:
# A string that starts with an alphabetic character, and continues for one or more characters of any kind.
SUFFIX = "(?P<suffix>[a-z].*)?"

split_pattern = re.compile("[^0-9a-z]", flags=re.IGNORECASE)
validation_pattern = re.compile("[0-9a-z]+", flags=re.IGNORECASE)
alphabetic_only_pattern = re.compile("[a-z]+", flags=re.IGNORECASE)
numeric_only_pattern = re.compile("[0-9]+")
versioned_string = re.compile("[a-z]+[0-9]+", flags=re.IGNORECASE)  # e.g. RC1, M5, etc.


def get_commit_from_version(git_obj: Git, purl: PackageURL) -> tuple[str, str]:
    """Try to find the matching commit in a repository of a given version via tags.

    The version of the passed PackageURL is used to match with the tags in the target repository.

    Parameters
    ----------
    git_obj: Git
        The repository.
    purl: PackageURL | None
        The PURL of the artifact.

    Returns
    -------
    tuple[str, str]
        The branch name and digest as a tuple.
    """
    if purl.version is None:
        logger.debug("Missing version for artifact: %s", purl.name)
        return "", ""
    logger.debug("Searching for commit of artifact version using tags: %s@%s", purl.name, purl.version)

    target_version_pattern, parts, has_non_numeric_suffix = _build_version_pattern(purl.version)

    # Only consider tags that have a commit.
    valid_tags = []
    for tag in git_obj.repo.tags:
        try:
            if not tag.commit:
                raise ValueError("The commit object is None")
        except ValueError:
            logger.debug("No commit found for tag: %s", tag)
            continue

        valid_tags.append(tag)

    if not valid_tags:
        logger.debug("No tags with commits found for %s", str(purl))
        return "", ""

    # Match tags.
    matched_tags = _match_tags(valid_tags, target_version_pattern, parts, has_non_numeric_suffix, purl.name)

    if not matched_tags:
        logger.debug("No tags matched for %s", str(purl))
        return "", ""

    if len(matched_tags) > 1:
        logger.debug("Tags found for %s: %s", str(purl), len(matched_tags))
        logger.debug("Best match: %s", matched_tags[0])
        logger.debug("Up to 5 others: %s", matched_tags[1:6])

    tag = matched_tags[0]
    tag_name = str(tag)
    branches = git_obj.get_commit_from_tag(tag_name).branches
    logger.debug("Branches: %s", branches)

    if not branches:
        logger.debug("No branch associated with tag (commit): %s (%s)", tag_name, tag.commit.hexsha)
        return "", ""

    branch_name = ""
    for branch in branches:
        # Ensure the detached head branch is not picked up.
        if "(HEAD detached at" not in branch:
            branch_name = branch
            break

    if not branch_name:
        logger.debug("No valid branch associated with tag (commit): %s (%s)", tag_name, tag.commit.hexsha)
        return "", ""

    logger.debug(
        "Found tag %s with commit %s of branch %s for artifact version %s@%s",
        tag,
        tag.commit.hexsha,
        branch_name,
        purl.name,
        purl.version,
    )
    return branch_name, tag.commit.hexsha


def _build_version_pattern(version: str) -> tuple[Pattern, list[str], bool]:
    """Build a version pattern to match the passed version string.

    Parameters
    ----------
    version: str
        The version string.

    Returns
    -------
    tuple[Pattern, list[str], bool]
        The tuple of the regex pattern that will match the version, the list of version parts that were extracted, and
        whether the version string has a non-numeric suffix.

    """
    # The version is split on non-alphanumeric characters to separate the version parts from the non-version parts.
    # e.g. 1.2.3-DEV -> [1, 2, 3, DEV]
    split = split_pattern.split(version)
    logger.debug("Split version: %s", split)
    if not split:
        # If the version string contains no separators use it as is.
        split = [version]

    this_version_pattern = ""
    parts = []
    numeric_parts = 0
    has_non_numeric_suffix = False
    for count, part in enumerate(split):
        # Validate the split part by checking it is only comprised of alphanumeric characters.
        valid = validation_pattern.match(part)
        if not valid:
            continue
        parts.append(part)

        # Detect versions that end with a zero, so the zero can be made optional.
        has_trailing_zero = len(split) > 2 and count == len(split) - 1 and part == "0"
        numeric_only = numeric_only_pattern.match(str(part))

        if not has_non_numeric_suffix and not numeric_only:
            # A non-numeric part enables the flag for treating this and all remaining parts as version suffix parts.
            has_non_numeric_suffix = True

        if has_trailing_zero or has_non_numeric_suffix:
            # This part will be made optional in the regex, hence the grouping bracket.
            this_version_pattern = this_version_pattern + "("

        if not has_non_numeric_suffix and numeric_only:
            # Keep track of version length for upcoming possible 'zero' digit extensions.
            numeric_parts = numeric_parts + 1

        if count == 1:
            this_version_pattern = this_version_pattern + INFIX_1
        elif count > 1:
            this_version_pattern = this_version_pattern + INFIX_3

        # Add the current part to the pattern.
        this_version_pattern = this_version_pattern + str(part)

        if has_trailing_zero or has_non_numeric_suffix:
            # Complete the optional capture group.
            this_version_pattern = this_version_pattern + ")?"

        # Extend the pattern with up to three additional zeros to help map mismatches between versions and tags.
        # E.g. 1.0 to 1.0.0, or 3.2 to 3.2.0, etc.
        if not has_non_numeric_suffix and count == len(split) - 1 and 1 < numeric_parts < 4:
            while numeric_parts < 4:
                # Additional zeros added for this purpose make use of a back reference to the first matched separator.
                this_version_pattern = this_version_pattern + "(" + INFIX_2 + "0)?"
                numeric_parts = numeric_parts + 1

    this_version_pattern = f"{PREFIX}{PREFIX_SEPARATOR}(?P<version>{this_version_pattern}){SUFFIX_SEPARATOR}{SUFFIX}$"
    return re.compile(this_version_pattern, flags=re.IGNORECASE), parts, has_non_numeric_suffix


def _match_tags(
    tag_list: list[TagReference], pattern: Pattern, parts: list[str], has_non_numeric_suffix: bool, artifact_name: str
) -> list[TagReference]:
    """Return items of the passed tag list that match the passed pattern.

    Parameters
    ----------
    tag_list: list[TagReference]
        The list of tags to check.
    pattern: Pattern
        The pattern to match against.
    parts: list[str]
        The list of version parts extracted from the version.
    has_non_numeric_suffix : bool
        Whether the version string has a non-numeric suffix.
    artifact_name : str
        The name of the artifact.

    Returns
    -------
    list[TagReference]
        The list of tags that matched the pattern.
    """
    matched_tags = []
    for tag in tag_list:
        tag_name = str(tag)
        match = pattern.match(tag_name)
        if not match:
            continue
        # Tags are append with their match information for possible further evaluation.
        matched_tags.append(
            {
                "tag": tag,
                "version": match.group("version"),
                "prefix": match.group("prefix"),
                "prefix_sep": match.group("prefix_sep"),
                "suffix_sep": match.group("suffix_sep"),
                "suffix": match.group("suffix"),
            }
        )

    if len(matched_tags) <= 1:
        return [_["tag"] for _ in matched_tags]

    # In the case of multiple matches, further work must be done.
    # Firstly, combine matches with their suffixes as some version patterns will not include the required suffix in the
    #  version group.
    if has_non_numeric_suffix:
        filtered_tags = []
        for item in matched_tags:
            # Discard tags with no suffix or with one that does not match the version.
            suffix: str | None = item["suffix"]
            if not suffix:
                filtered_tags.append(item)
                continue
            if suffix == parts[len(parts) - 1]:
                filtered_tags.append(item)
                continue

        matched_tags = filtered_tags

    # If any of the matches contain a prefix that matches the target artifact name, remove those that don't.
    named_tags = []
    for item in matched_tags:
        prefix: str | None = item["prefix"]
        if not prefix:
            continue
        if "/" in prefix:
            # Exclude prefix parts that exists before a forward slash, e.g. rel/
            split = prefix.split("/")
            prefix = split[len(split) - 1]
        if prefix.lower() == artifact_name.lower():
            named_tags.append(item)

    if named_tags:
        matched_tags = named_tags

    # If multiple tags still remain, sort them based on the closest match in terms of individual parts.
    if len(matched_tags) > 1:
        matched_tags.sort(
            key=lambda matched_tag: _count_parts_in_tag(matched_tag["version"], matched_tag["suffix"], parts)
        )

    return [_["tag"] for _ in matched_tags]


def _count_parts_in_tag(tag_version: str, tag_suffix: str, version_parts: list[str]) -> int:
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
    tag_version_text = tag_version
    for part in version_parts:
        if part in tag_version_text:
            tag_version_text.replace(part, "", 1)
            count = count - 1

    # Try to reduce the count further based on the tag suffix.
    if tag_suffix:
        last_part = version_parts[len(version_parts) - 1]
        # The tag suffix might consist of multiple version parts, e.g. RC1.RELEASE
        suffix_split = split_pattern.split(tag_suffix)
        if len(suffix_split) > 1:
            # Try to match suffix parts to version.
            versioned_string_match = False
            for suffix_part in suffix_split:
                if alphabetic_only_pattern.match(suffix_part) and suffix_part == last_part:
                    # If the suffix part only contains alphabetic characters, reduce the count if it
                    # matches the version.
                    count = count - 1
                    continue
                if versioned_string.match(suffix_part):
                    # If the suffix part contains alphabetic characters followed by numeric characters,
                    # reduce the count if it matches the version (once only), otherwise increase the count.
                    if not versioned_string_match and suffix_part == last_part:
                        count = count - 1
                        versioned_string_match = True
                    else:
                        count = count + 1
        else:
            # The tag suffix is a single part: reduce the count if it matches the version.
            if tag_suffix != last_part:
                count = count + 1
            else:
                count = count - 1

    return count
