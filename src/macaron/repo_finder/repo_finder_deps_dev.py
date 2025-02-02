# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the PythonRepoFinderDD class to be used for finding repositories using deps.dev."""
import json
import logging
from enum import StrEnum
from typing import Any
from urllib.parse import quote as encode

from packageurl import PackageURL

from macaron.json_tools import json_extract
from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_finder_enums import RepoFinderInfo
from macaron.repo_finder.repo_validator import find_valid_repository_url
from macaron.slsa_analyzer.git_url import clean_url
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

    # See https://docs.deps.dev/api/v3alpha/
    BASE_URL = "https://api.deps.dev/v3alpha/purl/"

    def find_repo(self, purl: PackageURL) -> tuple[str, RepoFinderInfo]:
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
            return "", RepoFinderInfo.DDEV_JSON_FETCH_ERROR

        urls, outcome = self._read_json(json_data)
        if not urls:
            logger.debug("Failed to extract repository URLs from json data: %s", purl)
            return "", outcome

        logger.debug("Found %s urls: %s", len(urls), urls)
        url = find_valid_repository_url(urls)
        if url:
            logger.debug("Found valid url: %s", url)
            return url, RepoFinderInfo.FOUND

        return "", RepoFinderInfo.DDEV_NO_URLS

    @staticmethod
    def get_project_info(project_url: str) -> dict[str, Any] | None:
        """Retrieve project information from deps.dev.

        Parameters
        ----------
        project_url : str
            The URL of the project.

        Returns
        -------
        dict[str, Any] | None
            The project information or None if the information could not be retrieved.
        """
        clean_repo_url = clean_url(project_url)
        if clean_repo_url is None or clean_repo_url.hostname is None:
            logger.debug("Invalid project url format: %s", project_url)
            return None

        project_key = clean_repo_url.hostname + clean_repo_url.path

        request_url = f"https://api.deps.dev/v3alpha/projects/{encode(project_key, safe='')}"
        response = send_get_http_raw(request_url)
        if not (response and response.text):
            logger.debug("Failed to retrieve additional repo info for: %s", project_url)
            return None

        try:
            response_json: dict = json.loads(response.text)
        except ValueError as error:
            logger.debug("Failed to parse response from deps.dev: %s", error)
            return None

        return response_json

    @staticmethod
    def get_latest_version(purl: PackageURL) -> tuple[PackageURL | None, RepoFinderInfo]:
        """Return a PURL representing the latest version of the passed artifact.

        Parameters
        ----------
        purl : PackageURL
            The current PURL.

        Returns
        -------
        tuple[PackageURL | None, RepoFinderInfo]
            The latest version of the PURL, or None if it could not be found, and the outcome to report.
        """
        if purl.version:
            namespace = purl.namespace + "/" if purl.namespace else ""
            purl = PackageURL.from_string(f"pkg:{purl.type}/{namespace}{purl.name}")

        url = f"{DepsDevRepoFinder.BASE_URL}{encode(str(purl), safe='')}"
        response = send_get_http_raw(url)

        if not response:
            return None, RepoFinderInfo.DDEV_BAD_RESPONSE

        try:
            metadata: dict = json.loads(response.text)
        except ValueError as error:
            logger.debug("Failed to parse response from deps.dev: %s", error)
            return None, RepoFinderInfo.DDEV_JSON_FETCH_ERROR

        versions_keys = ["package", "versions"] if "package" in metadata else ["version"]
        versions = json_extract(metadata, versions_keys, list)
        if not versions:
            return None, RepoFinderInfo.DDEV_JSON_INVALID
        latest_version = json_extract(versions[-1], ["versionKey", "version"], str)
        if not latest_version:
            return None, RepoFinderInfo.DDEV_JSON_INVALID

        namespace = purl.namespace + "/" if purl.namespace else ""
        return (
            PackageURL.from_string(f"pkg:{purl.type}/{namespace}{purl.name}@{latest_version}"),
            RepoFinderInfo.FOUND_FROM_LATEST,
        )

    def _create_urls(self, purl: PackageURL) -> tuple[list[str], RepoFinderInfo]:
        """
        Create the urls to search for the metadata relating to the passed artifact.

        If a version is not specified, remote API calls will be used to try and find one.

        Parameters
        ----------
        purl : PackageURL
            The PURL of an artifact.

        Returns
        -------
        list[str]
            The list of created URLs.
        """
        outcome = None
        if not purl.version:
            latest_purl, outcome = DepsDevRepoFinder.get_latest_version(purl)
            if not latest_purl:
                return [], outcome
            purl = latest_purl

        return [f"{DepsDevRepoFinder.BASE_URL}{encode(str(purl), safe='')}"], outcome or RepoFinderInfo.FOUND

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

    def _read_json(self, json_data: str) -> tuple[list[str], RepoFinderInfo]:
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
            return [], RepoFinderInfo.DDEV_JSON_FETCH_ERROR

        links_keys = ["version", "links"] if "version" in parsed else ["links"]
        links = json_extract(parsed, links_keys, list)
        if not links:
            logger.debug("Could not extract 'version' or 'links' from deps.dev response.")
            return [], RepoFinderInfo.DDEV_JSON_INVALID

        result = []
        for item in links:
            url = item.get("url")
            if url and isinstance(url, str):
                result.append(url)

        return result, RepoFinderInfo.FOUND
