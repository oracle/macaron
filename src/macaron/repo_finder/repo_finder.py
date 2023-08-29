# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic for using/calling the different repo finders."""

import logging
import os
from urllib.parse import ParseResult, urlunparse

from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.dependency_analyzer import DependencyAnalyzer
from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_finder_deps_dev import RepoFinderDepsDev
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
        repo_finder = RepoFinderDepsDev(purl.type)
    else:
        logger.debug("No Repo Finder found for package type: %s of %s", purl.type, purl.to_string())
        return ""

    # Call Repo Finder and return first valid URL
    logger.debug("Analyzing %s with Repo Finder: %s", purl.to_string(), repo_finder.__class__)
    found_urls = repo_finder.find_repo(purl.namespace or "", purl.name, purl.version or "")
    return DependencyAnalyzer.find_valid_url(found_urls)


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

    - The supprted git service domains (e.g. ``github.com``) defined in ``available_domains``.

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
        logger.error("The PURL type of %s is not valid as a repository type.", purl.to_string())
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
