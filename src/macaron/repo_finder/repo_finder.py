# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic for using/calling the different repo finders."""

import logging
from collections.abc import Iterator

from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_finder_dd import RepoFinderDD
from macaron.repo_finder.repo_finder_java import JavaRepoFinder

logger: logging.Logger = logging.getLogger(__name__)


def find_repo(purl_string: str) -> Iterator[str]:
    """Retrieve the repository URL that matches the given PURL.

    Parameters
    ----------
    purl_string : str
        The purl string representing a package.

    Yields
    ------
    Iterator[str] :
        The repository URLs found for the passed package.
    """
    # Parse the purl string
    try:
        purl = PackageURL.from_string(purl_string)
    except ValueError as error:
        logger.debug("Invalid PURL: %s, %s", purl_string, error)
        return

    # Find matching Repo Finder
    repo_finder: BaseRepoFinder
    if purl.type == "maven":
        repo_finder = JavaRepoFinder()
    elif purl.type in ["pypi", "nuget", "cargo", "npm"] and defaults.getboolean(
        "repofinder", "use_open_source_insights"
    ):
        repo_finder = RepoFinderDD(purl.type)
    else:
        logger.debug("No Repo Finder found for package type: %s of %s", purl.type, purl_string)
        return

    # Call Repo Finder
    logger.debug("Analyzing %s with Repo Finder: %s", purl_string, repo_finder.__class__)
    yield from repo_finder.find_repo(purl.namespace or "", purl.name, purl.version or "")
