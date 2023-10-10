# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module contains the logic for using/calling the different repo finders.

Input
-----
The entry point of the repo finder depends on the type of PURL being analyzed.
- If passing a PURL representing an artifact, the ``find_repo`` function in this file should be called.
- If passing a PURL representing a repository, the ``to_repo_path`` function in this file should be called.

Artifact PURLs
--------------
For artifact PURLs, the PURL type determines how the repositories are searched for.
Currently, for Maven PURLs, SCM meta data is retrieved from the matching POM retrieved from Maven Central (or
other configured location).

For Python, .NET, Rust, and NodeJS type PURLs, Google's Open Source Insights API is used to find the meta data.

In either case, any repository links are extracted from the meta data, then checked for validity via
``repo_validator::find_valid_repository_url`` which accepts URLs that point to a Github repository or similar.

Repository PURLs
----------------
For repository PURLs, the type is checked against the configured valid domains, and accepted or rejected based
on that data.

Result
------
If all goes well, a repository URL that matches the initial artifact or repository PURL will be returned for
analysis.
"""

import logging
import os
import re
from re import Pattern
from urllib.parse import ParseResult, urlunparse

from packageurl import PackageURL
from packaging import version
from pydriller import Git

from macaron.config.defaults import defaults
from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_finder_deps_dev import DepsDevRepoFinder
from macaron.repo_finder.repo_finder_java import JavaRepoFinder

logger: logging.Logger = logging.getLogger(__name__)

# This regex is used to find matching version strings in repository tags.
# (.+-)? - Optional prefix text before a hyphen.
# r? -- Optional version prefix used by some tags, probably denoting Release.
# (?P<version>{version.VERSION_PATTERN}) - A named group that uses the version regex from the packaging library.
# (\\#.+)? - Optional suffix text after a hash symbol.
# $ - perform match from the end of the string.
# VERBOSE and IGNORECASE flags are required by the packaging library.
tag_pattern: Pattern = re.compile(
    f"(.*-)?r?(?P<version>{version.VERSION_PATTERN})(\\#.+)?$", flags=re.VERBOSE | re.IGNORECASE
)


def find_repo(purl: PackageURL) -> str:
    """Retrieve the repository URL that matches the given PURL.

    Parameters
    ----------
    purl : PackageURL
        The parsed PURL to convert to the repository path.

    Returns
    -------
    str :
        The repository URL found for the passed package.
    """
    repo_finder: BaseRepoFinder
    if purl.type == "maven":
        repo_finder = JavaRepoFinder()
    elif defaults.getboolean("repofinder", "use_open_source_insights") and purl.type in [
        "pypi",
        "nuget",
        "cargo",
        "npm",
    ]:
        repo_finder = DepsDevRepoFinder()
    else:
        logger.debug("No Repo Finder found for package type: %s of %s", purl.type, purl.to_string())
        return ""

    # Call Repo Finder and return first valid URL
    logger.debug("Analyzing %s with Repo Finder: %s", purl.to_string(), repo_finder.__class__)
    return repo_finder.find_repo(purl)


def to_domain_from_known_purl_types(purl_type: str) -> str | None:
    """Return the git service domain from a known web-based purl type.

    This method is used to handle cases where the purl type value is not the git domain but a pre-defined
    repo-based type in https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst.

    Note that this method will be updated when there are new pre-defined types as per the PURL specification.

    Parameters
    ----------
    purl_type : str
        The type field of the PURL.

    Returns
    -------
    str | None
        The git service domain corresponding to the purl type or None if the purl type is unknown.
    """
    known_types = {"github": "github.com", "bitbucket": "bitbucket.org"}
    return known_types.get(purl_type, None)


def to_repo_path(purl: PackageURL, available_domains: list[str]) -> str | None:
    """Return the repository path from the PURL string.

    This method only supports converting a PURL with the following format:

        pkg:<type>/<namespace>/<name>[...]

    Where ``type`` could be either:
    - The pre-defined repository-based PURL type as defined in
    https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst

    - The supported git service domains (e.g. ``github.com``) defined in ``available_domains``.

    The repository path will be generated with the following format ``https://<type>/<namespace>/<name>``.

    Parameters
    ----------
    purl : PackageURL
        The parsed PURL to convert to the repository path.
    available_domains: list[str]
        The list of available domains

    Returns
    -------
    str | None
        The URL to the repository which the PURL is referring to or None if we cannot convert it.
    """
    domain = to_domain_from_known_purl_types(purl.type) or (purl.type if purl.type in available_domains else None)
    if not domain:
        logger.info(
            "The PURL type of %s is not valid as a repository type. Trying to find the repository...", purl.to_string()
        )
        # Try to find the repository
        return find_repo(purl)

    if not purl.namespace:
        logger.error("Expecting a non-empty namespace from %s.", purl.to_string())
        return None

    # TODO: Handle the version tag and commit digest if they are given in the PURL.
    return urlunparse(
        ParseResult(
            scheme="https",
            netloc=domain,
            path=os.path.join(purl.namespace, purl.name),
            params="",
            query="",
            fragment="",
        )
    )


def get_commit_from_version_tag(git_obj: Git, purl: PackageURL) -> tuple[str, str]:
    """Try to find the matching commit in a repository of a given version via tags.

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
    # Try to resolve the branch and digest from the version
    logger.debug("Searching for commit of artifact version using tags: %s@%s", purl.name, purl.version)
    matched_tags = []
    # Iterate over tags, keeping any that match the regex version pattern, contain the purl.name, and/or match the
    # specific version.
    # If any tags contain the purl.name of the artifact and a valid version, tags that only contain the version
    # will be ignored.
    tag_count = 0
    require_name_match = False
    for tag in git_obj.repo.tags:
        tag_count = tag_count + 1
        if not tag.commit:
            continue

        tag_name = str(tag)
        adjusted_tag_name = tag_name
        contains_name = False
        if purl.name.lower() in tag_name.lower():
            adjusted_tag_name = re.sub(purl.name, "", adjusted_tag_name, re.IGNORECASE)
            contains_name = True

        match = tag_pattern.match(adjusted_tag_name)
        logger.debug("Tag %s vs. Version %s -- Match: %s", tag_name, purl.version, match.group() if match else None)

        if not require_name_match and match and match.group("version") and contains_name:
            require_name_match = True

        if not match:
            continue

        match_value = str(match.group("version"))
        if (
            match_value.startswith("v")
            or match_value.startswith("r")
            or match_value.startswith("V")
            or match_value.startswith("R")
        ):
            # Remove version prefix
            match_value = match_value[1:]

        if match_value == purl.version:
            if contains_name:
                matched_tags.append(tag)
            elif not require_name_match:
                matched_tags.append(tag)

    if tag_count == 0:
        logger.debug("No tags found for %s", str(purl))
    elif tag_count > 0:
        logger.debug("Tags found for %s: %s", str(purl), tag_count)

    for tag in matched_tags:
        if len(matched_tags) > 1:
            # TODO decide how to handle multiple matching tags, and if it is possible
            logger.debug("Found multiple tags for %s: %s", str(purl), len(matched_tags))
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
