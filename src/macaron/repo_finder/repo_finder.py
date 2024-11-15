# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
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
``repo_validator::find_valid_repository_url`` which accepts URLs that point to a GitHub repository or similar.

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
from urllib.parse import ParseResult, urlunparse

from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.repo_finder import to_domain_from_known_purl_types
from macaron.repo_finder.commit_finder import match_tags
from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_finder_deps_dev import DepsDevRepoFinder
from macaron.repo_finder.repo_finder_java import JavaRepoFinder
from macaron.repo_finder.repo_utils import generate_report, prepare_repo
from macaron.slsa_analyzer.git_url import GIT_REPOS_DIR, list_remote_references

logger: logging.Logger = logging.getLogger(__name__)


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
    elif defaults.getboolean("repofinder", "use_open_source_insights") and purl.type in {
        "pypi",
        "nuget",
        "cargo",
        "npm",
    }:
        repo_finder = DepsDevRepoFinder()
    else:
        logger.debug("No Repo Finder found for package type: %s of %s", purl.type, purl)
        return ""

    # Call Repo Finder and return first valid URL
    logger.debug("Analyzing %s with Repo Finder: %s", purl, type(repo_finder))
    return repo_finder.find_repo(purl)


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
        logger.info("The PURL type of %s is not valid as a repository type. Trying to find the repository...", purl)
        # Try to find the repository
        return find_repo(purl)

    if not purl.namespace:
        logger.error("Expecting a non-empty namespace from %s.", purl)
        return None

    # If the PURL contains a commit digest or version tag, they will be used after the repository has been resolved.
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


def find_source(purl_string: str, input_repo: str | None) -> bool:
    """Perform repo and commit finding for a passed PURL, or commit finding for a passed PURL and repo.

    Parameters
    ----------
    purl_string: str
        The PURL string of the target.
    input_repo: str | None
        The repository path optionally provided by the user.

    Returns
    -------
    bool
        True if the source was found.
    """
    try:
        purl = PackageURL.from_string(purl_string)
    except ValueError as error:
        logger.error("Could not parse PURL: %s", error)
        return False

    if not purl.version:
        logger.debug("PURL is missing version.")
        return False

    found_repo = input_repo
    if not input_repo:
        logger.debug("Searching for repo of PURL: %s", purl)
        found_repo = find_repo(purl)

    if not found_repo:
        logger.error("Could not find repo for PURL: %s", purl)
        return False

    # Disable other loggers for cleaner output.
    logging.getLogger("macaron.slsa_analyzer.analyzer").disabled = True

    if defaults.getboolean("repofinder", "find_source_should_clone"):
        logger.debug("Preparing repo: %s", found_repo)
        repo_dir = os.path.join(global_config.output_path, GIT_REPOS_DIR)
        logging.getLogger("macaron.slsa_analyzer.git_url").disabled = True
        git_obj = prepare_repo(
            repo_dir,
            found_repo,
            purl=purl,
        )

        if not git_obj:
            # TODO expand this message to cover cases where the obj was not created due to lack of correct tag.
            logger.error("Could not resolve repository: %s", found_repo)
            return False

        try:
            digest = git_obj.get_head().hash
        except ValueError:
            logger.debug("Could not retrieve commit hash from repository.")
            return False
    else:
        # Retrieve the tags.
        tags = get_tags_via_git_remote(found_repo)
        if not tags:
            return False

        matches = match_tags(list(tags.keys()), purl.name, purl.version)

        if not matches:
            return False

        matched_tag = matches[0]
        digest = tags[matched_tag]

    if not digest:
        logger.error("Could not find commit for purl / repository: %s / %s", purl, found_repo)
        return False

    if not input_repo:
        logger.info("Found repository for PURL: %s", found_repo)

    logger.info("Found commit for PURL: %s", digest)

    if not generate_report(purl_string, digest, found_repo, os.path.join(global_config.output_path, "reports")):
        return False

    return True


def get_tags_via_git_remote(repo: str) -> dict[str, str] | None:
    """Retrieve all tags from a given repository using ls-remote.

    Parameters
    ----------
    repo: str
        The repository to perform the operation on.

    Returns
    -------
    dict[str]
        A dictionary of tags mapped to their commits, or None if the operation failed..
    """
    tag_data = list_remote_references(["--tags"], repo)
    if not tag_data:
        return None
    tags = {}

    for tag_line in tag_data.splitlines():
        tag_line = tag_line.strip()
        if not tag_line:
            continue
        split = tag_line.split("\t")
        if len(split) != 2:
            continue
        possible_tag = split[1]
        if possible_tag.endswith("^{}"):
            possible_tag = possible_tag[:-3]
        elif possible_tag in tags:
            # If a tag already exists, it must be the annotated reference of an annotated tag.
            # In that case we skip the tag as it does not point to the proper source commit.
            # Note that this should only happen if the tags are received out of standard order.
            continue
        possible_tag = possible_tag.replace("refs/tags/", "")
        if not possible_tag:
            continue
        tags[possible_tag] = split[0]

    logger.debug("Found %s tags via ls-remote of %s", len(tags), repo)

    return tags
