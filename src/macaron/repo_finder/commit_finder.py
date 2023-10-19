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

ALPHANUMERIC = "0-9a-z"
PREFIX = "(?:.*)"
INFIX = "[^0-9]{1,3}"  # 1 to 3 non-numeric characters
split_pattern = re.compile(f"[^{ALPHANUMERIC}]+", flags=re.IGNORECASE)
validation_pattern = re.compile(f"[{ALPHANUMERIC}]+", flags=re.IGNORECASE)


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

    target_version_pattern = _build_version_pattern(purl.version)
    has_name_pattern = re.compile(f".*{purl.name}.*[0-9].*", flags=re.IGNORECASE)

    # Tags are examined as followed:
    # - Any without a corresponding commit are discarded.
    # - If any tag matches the has_name_pattern, only tags that match it will be examined.
    # - If no tag matches the has_name_pattern, all tags will be examined.
    named_tags: list[TagReference] = []
    other_tags: list[TagReference] = []
    for tag in git_obj.repo.tags:
        try:
            if not tag.commit:
                raise ValueError("The commit object is None")
        except ValueError:
            logger.debug("No commit found for tag: %s", tag)
            continue

        tag_name = str(tag)

        if has_name_pattern.match(tag_name):
            named_tags.append(tag)
        else:
            other_tags.append(tag)

    # Match tags.
    if named_tags:
        matched_tags = _match_tags(named_tags, target_version_pattern)
    else:
        matched_tags = _match_tags(other_tags, target_version_pattern)

    # Report matched tags.
    if not matched_tags:
        logger.debug("No tags found for %s", str(purl))
    else:
        logger.debug("Tags found for %s: %s", str(purl), len(matched_tags))

    if len(matched_tags) > 1:
        # TODO decide how to handle multiple matching tags, and if it is possible
        logger.debug("Found multiple tags for %s: %s", str(purl), len(matched_tags))

    for tag in matched_tags:
        tag_name = str(tag)
        branches = git_obj.get_commit_from_tag(tag_name).branches

        logger.debug("Branches: %s", branches)

        if not branches:
            continue

        branch_name = ""
        for branch in branches:
            # Ensure the detached head branch is not picked up.
            if "(HEAD detached at" not in branch:
                branch_name = branch
                break

        if not branch_name:
            continue

        logger.debug(
            "Found tag %s with commit %s of branch %s for artifact version %s@%s",
            tag,
            tag.commit.hexsha,
            branch_name,
            purl.name,
            purl.version,
        )
        return branch_name, tag.commit.hexsha

    logger.debug("Could not find tagged commit for artifact version: %s@%s", purl.name, purl.version)
    return "", ""


def _build_version_pattern(version: str) -> Pattern:
    """Build a version pattern to match the passed version string.

    Parameters
    ----------
    version: str
        The version string.

    Returns
    -------
    Pattern
        The regex pattern that will match the version.

    """
    # The version is split on non-alphanumeric characters to separate the version parts from the non-version parts.
    # e.g. 1.2.3-DEV -> [1, 2, 3, DEV]
    split = split_pattern.split(version)
    logger.debug("Split version: %s", split)
    if not split:
        # If the version string contains no separators use it as is.
        split = [version]

    this_version_pattern = ""
    for part in split:
        # Validate the split part by checking it is only comprised of alphanumeric characters.
        valid = validation_pattern.match(part)
        if not valid:
            continue
        if this_version_pattern:
            # Between one and three non-numeric characters are accepted between the version parts.
            # This balances the tradeoff between maximal matching and minimal false positives.
            this_version_pattern = this_version_pattern + INFIX
        this_version_pattern = this_version_pattern + str(part)

    # Prepend the optional prefix, add a named capture group for the version, and enforce end of string analysis.
    this_version_pattern = PREFIX + "(?P<version>" + this_version_pattern + ")" + "$"
    logger.debug("Created pattern: %s", this_version_pattern)
    return re.compile(this_version_pattern, flags=re.IGNORECASE)


def _match_tags(tag_list: list[TagReference], pattern: Pattern) -> list[TagReference]:
    """Return items of the passed tag list that match the passed pattern.

    Parameters
    ----------
    tag_list: list[TagReference]
        The list of tags to check.
    pattern: Pattern
        The pattern to match against.

    Returns
    -------
    The list of tags that matched the pattern.
    """
    matched_tags = []
    for tag in tag_list:
        tag_name = str(tag)
        match = pattern.match(tag_name)
        if not match:
            continue
        matched_tags.append(tag)
    return matched_tags
