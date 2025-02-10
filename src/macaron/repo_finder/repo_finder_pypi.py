# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic for finding repositories of PyPI projects."""
import logging
import urllib.parse

from packageurl import PackageURL

from macaron.errors import InvalidHTTPResponseError
from macaron.json_tools import json_extract
from macaron.repo_finder.repo_finder_enums import RepoFinderInfo
from macaron.slsa_analyzer.package_registry import PyPIRegistry

logger: logging.Logger = logging.getLogger(__name__)


def find_repo(purl: PackageURL) -> tuple[str, RepoFinderInfo]:
    """Retrieve the repository URL that matches the given PyPI PURL.

    Parameters
    ----------
    purl : PackageURL
        The parsed PURL to convert to the repository path.

    Returns
    -------
    tuple[str, RepoFinderOutcome] :
        The repository URL for the passed package, if found, and the outcome to report.
    """
    pypi_registry = PyPIRegistry()
    pypi_registry.load_defaults()
    json_endpoint = f"pypi/{purl.name}/json"
    url = urllib.parse.urljoin(pypi_registry.registry_url, json_endpoint)
    try:
        json = pypi_registry.download_package_json(url)
    except InvalidHTTPResponseError as error:
        logger.debug(error)
        # TODO improve accuracy of this outcome.
        return "", RepoFinderInfo.PYPI_HTTP_ERROR

    url_dict = json_extract(json, ["info", "project_urls"], dict)
    if not url_dict:
        return "", RepoFinderInfo.PYPI_JSON_ERROR

    for url_key in url_dict:
        url = url_dict[url_key]
        parsed_url = urllib.parse.urlparse(url)
        if not parsed_url.hostname:
            continue
        if not parsed_url.hostname.lower() == "github.com":
            continue
        # The path starts with a "/".
        split_path = parsed_url.path[1:].split("/")
        if not split_path or len(split_path) < 2:
            continue
        # Fix the URL so that it is the base GitHub URL. E.g. github.com/{owner}/{repo}
        fixed_url = urllib.parse.ParseResult(
            scheme=parsed_url.scheme,
            netloc=parsed_url.netloc,
            path=f"{split_path[0]}/{split_path[1]}",
            params=parsed_url.params,
            query=parsed_url.query,
            fragment=parsed_url.fragment,
        ).geturl()
        logger.debug("Found repository URL from PyPI: %s", fixed_url)
        return fixed_url, RepoFinderInfo.FOUND_FROM_PYPI

    return "", RepoFinderInfo.PYPI_NO_URLS
