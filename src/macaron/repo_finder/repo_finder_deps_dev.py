# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
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

    def find_repo(self, purl: PackageURL) -> str:
        """
        Attempt to retrieve a repository URL that matches the passed artifact.

        Parameters
        ----------
        purl : PackageURL
            The PURL of an artifact.

        Returns
        -------
        str :
            The URL of the found repository.
        """
        request_urls = self._create_urls(purl)
        if not request_urls:
            logger.debug("No urls found for: %s", purl)
            return ""

        json_data = self._retrieve_json(request_urls[0])
        if not json_data:
            logger.debug("Failed to retrieve json data for: %s", purl)
            return ""

        urls = self._read_json(json_data)
        if not urls:
            logger.debug("Failed to extract repository URLs from json data: %s", purl)
            return ""

        logger.debug("Found %s urls: %s", len(urls), urls)
        url = find_valid_repository_url(urls)
        if url:
            logger.debug("Found valid url: %s", url)
            return url

        return ""

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
        if response is None or not response.text:
            logger.debug("Failed to retrieve additional repo info for: %s", project_url)
            return None

        try:
            response_json: dict = json.loads(response.text)
        except ValueError as error:
            logger.debug("Failed to parse response from deps.dev: %s", error)
            return None

        return response_json

    def _create_urls(self, purl: PackageURL) -> list[str]:
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
        # See https://docs.deps.dev/api/v3alpha/
        base_url = f"https://api.deps.dev/v3alpha/purl/{encode(str(purl)).replace('/', '%2F')}"

        if not base_url:
            return []

        if purl.version:
            return [base_url]

        # Find the latest version.
        response = send_get_http_raw(base_url, {})

        if not response:
            return []

        try:
            metadata: dict = json.loads(response.text)
        except ValueError as error:
            logger.debug("Failed to parse response from deps.dev: %s", error)
            return []

        versions_keys = ["package", "versions"] if "package" in metadata else ["version"]
        versions = json_extract(metadata, versions_keys, list)
        if not versions:
            return []
        latest_version = json_extract(versions[-1], ["versionKey", "version"], str)
        if not latest_version:
            return []

        logger.debug("Found latest version: %s", latest_version)
        return [f"{base_url}%40{latest_version}"]

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

    def _read_json(self, json_data: str) -> list[str]:
        """
        Parse the deps.dev json file and extract the repository links.

        Parameters
        ----------
        json_data : str
            The json metadata as a string.

        Returns
        -------
        list[str] :
            The extracted contents as a list of strings.
        """
        try:
            parsed = json.loads(json_data)
        except ValueError as error:
            logger.debug("Failed to parse response from deps.dev: %s", error)
            return []

        links_keys = ["version", "links"] if "version" in parsed else ["links"]
        links = json_extract(parsed, links_keys, list)
        if not links:
            logger.debug("Could not extract 'version' or 'links' from deps.dev response.")
            return []

        result = []
        for item in links:
            url = item.get("url")
            if url and isinstance(url, str):
                result.append(url)

        return result
