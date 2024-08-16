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
from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_finder_deps_dev import DepsDevRepoFinder
from macaron.repo_finder.repo_finder_java import JavaRepoFinder

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
    elif defaults.getboolean("repofinder", "use_open_source_insights") and purl.type in [
        "pypi",
        "nuget",
        "cargo",
        "npm",
    ]:
        repo_finder = DepsDevRepoFinder()
    else:
        logger.debug("No Repo Finder found for package type: %s of %s", purl.type, purl)
        return ""

    # Call Repo Finder and return first valid URL
    logger.debug("Analyzing %s with Repo Finder: %s", purl, type(repo_finder))
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


def find_source(purl_string: str, repo: str | None) -> bool:
    """Perform repo and commit finding for a passed PURL, or commit finding for a passed PURL and repo.

    Parameters
    ----------
    purl_string: str
        The PURL string of the target.
    repo: str | None
        The optional repository path.

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

    found_repo = repo
    if not repo:
        logger.debug("Searching for repo of PURL: %s", purl)
        found_repo = find_repo(purl)

    if not found_repo:
        logger.error("Could not find repo for PURL: %s", purl)
        return False

    # Disable other loggers for cleaner output.
    analyzer_logger = logging.getLogger("macaron.slsa_analyzer.analyzer")
    analyzer_logger.disabled = True
    git_logger = logging.getLogger("macaron.slsa_analyzer.git_url")
    git_logger.disabled = True

    # Prepare the repo.
    logger.debug("Preparing repo: %s", found_repo)
    # Importing here to avoid cyclic import problem.
    from macaron.slsa_analyzer.analyzer import Analyzer  # pylint: disable=import-outside-toplevel, cyclic-import

    analyzer = Analyzer(global_config.output_path, global_config.build_log_path)
    repo_dir = os.path.join(analyzer.output_path, analyzer.GIT_REPOS_DIR)
    git_obj = analyzer.prepare_repo(repo_dir, found_repo, "", "", purl)

    if not git_obj:
        # TODO expand this message to cover cases where the obj was not created due to lack of correct tag.
        logger.error("Could not resolve repository: %s", found_repo)
        return False

    try:
        digest = git_obj.get_head().hash
    except ValueError:
        logger.debug("Could not retrieve commit hash from repository.")
        return False

    if not digest:
        logger.error("Could not find commit for purl / repository: %s / %s", purl, found_repo)
        return False

    if not repo:
        logger.info("Found repository for PURL: %s", found_repo)
    logger.info("Found commit for PURL: %s", digest)

    logger.info("%s/commit/%s", found_repo, digest)

    return True
