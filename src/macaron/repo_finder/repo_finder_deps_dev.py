# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the PythonRepoFinderDD class to be used for finding repositories using deps.dev."""
import json
import logging
import urllib.parse
from enum import StrEnum
from urllib.parse import quote as encode

from packageurl import PackageURL

from macaron.json_tools import json_extract
from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_finder_enums import RepoFinderOutcome
from macaron.repo_finder.repo_validator import find_valid_repository_url
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class DepsDevType(StrEnum):
    """
    The package manager types supported by deps.dev.

    This enum should be updated based on updates to deps.dev.
    """

    MAVEN = "maven"
    PYPI = "pypi"
    NUGET = "nuget"
    CARGO = "cargo"
    NPM = "npm"


class DepsDevRepoFinder(BaseRepoFinder):
    """This class is used to find repositories using Google's Open Source Insights A.K.A. deps.dev."""

    def find_repo(self, purl: PackageURL) -> tuple[str, RepoFinderOutcome]:
        """
        Attempt to retrieve a repository URL that matches the passed artifact.

        Parameters
        ----------
        purl : PackageURL
            The PURL of an artifact.

        Returns
        -------
        tuple[str, RepoFinderOutcome] :
            A tuple of the found URL (or an empty string), and the outcome of the Repo Finder.
        """
        request_urls, outcome = self._create_urls(purl)
        if not request_urls:
            logger.debug("No urls found for: %s", purl)
            return "", outcome

        json_data = self._retrieve_json(request_urls[0])
        if not json_data:
            logger.debug("Failed to retrieve json data for: %s", purl)
            return "", RepoFinderOutcome.DDEV_JSON_FETCH_ERROR

        urls, outcome = self._read_json(json_data)
        if not urls:
            logger.debug("Failed to extract repository URLs from json data: %s", purl)
            return "", outcome

        logger.debug("Found %s urls: %s", len(urls), urls)
        url = find_valid_repository_url(urls)
        if url:
            logger.debug("Found valid url: %s", url)
            return url, RepoFinderOutcome.FOUND

        return "", RepoFinderOutcome.DDEV_NO_URLS

    def _create_urls(self, purl: PackageURL) -> tuple[list[str], RepoFinderOutcome]:
        """
        Create the urls to search for the metadata relating to the passed artifact.

        If a version is not specified, remote API calls will be used to try and find one.

        Parameters
        ----------
        purl : PackageURL
            The PURL of an artifact.

        Returns
        -------
        tuple[list[str], RepoFinderOutcome]
            The list of created URLs, if any, and the outcome to report.
        """
        # See https://docs.deps.dev/api/v3alpha/

        base_url = urllib.parse.ParseResult(
            scheme="https",
            netloc="api.deps.dev",
            path="/".join(["v3alpha", "purl", encode(str(purl)).replace("/", "%2F")]),
            params="",
            query="",
            fragment="",
        ).geturl()

        if purl.version:
            return [base_url], RepoFinderOutcome.FOUND

        # Find the latest version.
        response = send_get_http_raw(base_url, {})

        if not response:
            return [], RepoFinderOutcome.DDEV_BAD_RESPONSE

        try:
            metadata: dict = json.loads(response.text)
        except ValueError as error:
            logger.debug("Failed to parse response from deps.dev: %s", error)
            return [], RepoFinderOutcome.DDEV_JSON_FETCH_ERROR

        versions_keys = ["package", "versions"] if "package" in metadata else ["version"]
        versions = json_extract(metadata, versions_keys, list)
        if not versions:
            return [], RepoFinderOutcome.DDEV_JSON_INVALID
        latest_version = json_extract(versions[-1], ["versionKey", "version"], str)
        if not latest_version:
            return [], RepoFinderOutcome.DDEV_JSON_INVALID

        logger.debug("Found latest version: %s", latest_version)
        return [f"{base_url}%40{latest_version}"], RepoFinderOutcome.FOUND

    def _retrieve_json(self, url: str) -> str:
        """
        Attempt to retrieve the json file located at the passed URL.

        Parameters
        ----------
        url : str
            The URL for the GET request.

        Returns
        -------
        str :
            The retrieved file data or an empty string.
        """
        response = send_get_http_raw(url, {})

        if not response:
            return ""

        return response.text

    def _read_json(self, json_data: str) -> tuple[list[str], RepoFinderOutcome]:
        """
        Parse the deps.dev json file and extract the repository links.

        Parameters
        ----------
        json_data : str
            The json metadata as a string.

        Returns
        -------
        tuple[list[str], RepoFinderOutcome] :
            The extracted contents as a list, and the outcome to report.
        """
        try:
            parsed = json.loads(json_data)
        except ValueError as error:
            logger.debug("Failed to parse response from deps.dev: %s", error)
            return [], RepoFinderOutcome.DDEV_JSON_FETCH_ERROR

        links_keys = ["version", "links"] if "version" in parsed else ["links"]
        links = json_extract(parsed, links_keys, list)
        if not links:
            logger.debug("Could not extract 'version' or 'links' from deps.dev response.")
            return [], RepoFinderOutcome.DDEV_JSON_INVALID

        result = []
        for item in links:
            url = item.get("url")
            if url and isinstance(url, str):
                result.append(url)

        return result, RepoFinderOutcome.FOUND
