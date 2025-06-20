# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the PythonRepoFinderDD class to be used for finding repositories using deps.dev."""
import json
import logging
import urllib.parse
from enum import StrEnum
from typing import Any
from urllib.parse import quote as encode

from packageurl import PackageURL

from macaron.errors import APIAccessError
from macaron.json_tools import json_extract
from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_finder_enums import RepoFinderInfo
from macaron.repo_finder.repo_validator import find_valid_repository_url
from macaron.slsa_analyzer.git_url import clean_url
from macaron.slsa_analyzer.package_registry import PyPIRegistry
from macaron.slsa_analyzer.package_registry.deps_dev import DepsDevService
from macaron.util import send_get_http, send_get_http_raw

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
        if not purl.version:
            latest_purl, outcome = self.get_latest_version(purl)
            if not latest_purl:
                return "", outcome
            purl = latest_purl

        try:
            json_data = DepsDevService.get_package_info(str(purl))
        except APIAccessError:
            return "", RepoFinderInfo.DDEV_API_ERROR

        urls, outcome = DepsDevRepoFinder.extract_links(json_data)
        if not urls:
            logger.debug("Failed to extract repository URLs from json data: %s", purl)
            return "", outcome

        logger.debug("Found %s urls: %s", len(urls), urls)
        url = find_valid_repository_url(urls)
        if url:
            logger.debug("Found valid url: %s", url)
            return url, RepoFinderInfo.FOUND

        return "", RepoFinderInfo.DDEV_NO_VALID_URLS

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

        api_endpoint = DepsDevService.get_endpoint(f"projects/{encode(project_key, safe='')}")
        request_url = urllib.parse.urlunsplit(api_endpoint)

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

        try:
            metadata = DepsDevService.get_package_info(purl)
        except APIAccessError:
            return None, RepoFinderInfo.DDEV_API_ERROR

        versions_keys = ["package", "versions"] if "package" in metadata else ["version"]
        versions = json_extract(metadata, versions_keys, list)
        if not versions:
            return None, RepoFinderInfo.DDEV_JSON_INVALID

        latest_version = None
        for version_result in reversed(versions):
            if not isinstance(version_result, dict) or "isDefault" not in version_result:
                continue
            if version_result["isDefault"]:
                # Accept the version as the latest if it is marked with the "isDefault" property.
                latest_version = json_extract(version_result, ["versionKey", "version"], str)
                break

        if not latest_version:
            logger.debug("No latest version found in version list: %s", len(versions))
            return None, RepoFinderInfo.DDEV_JSON_INVALID

        namespace = purl.namespace + "/" if purl.namespace else ""
        return (
            PackageURL.from_string(f"pkg:{purl.type}/{namespace}{purl.name}@{latest_version}"),
            RepoFinderInfo.FOUND_FROM_LATEST,
        )

    @staticmethod
    def get_attestation(purl: PackageURL) -> tuple[dict | None, str | None, bool]:
        """Retrieve the attestation associated with the passed PURL.

        Parameters
        ----------
        purl : PackageURL
            The PURL of an artifact.

        Returns
        -------
        tuple[dict | None, str | None, bool]
            The attestation, or None if not found, the url of the attestation asset,
            and a flag for whether the attestation is verified.
        """
        if purl.type != "pypi":
            logger.debug("PURL type (%s) attestation not yet supported via deps.dev.")
            return None, None, False

        if not purl.version:
            latest_purl, _ = DepsDevRepoFinder.get_latest_version(purl)
            if not latest_purl:
                return None, None, False
            purl = latest_purl

        # Example of a PURL endpoint for deps.dev with '/' encoded as '%2F':
        # https://api.deps.dev/v3alpha/purl/pkg:npm%2F@sigstore%2Fmock@0.7.5
        purl_endpoint = DepsDevService.get_purl_endpoint(purl)
        target_url = urllib.parse.urlunsplit(purl_endpoint)

        result = send_get_http(target_url, headers={})
        if not result:
            return None, None, False

        attestation_keys = ["attestations"]
        if "version" in result:
            attestation_keys.insert(0, "version")

        result_attestations = json_extract(result, attestation_keys, list)
        if not result_attestations:
            logger.debug("No attestations in result.")
            return None, None, False
        if len(result_attestations) > 1:
            logger.debug("More than one attestation in result: %s", len(result_attestations))

        attestation_url = json_extract(result_attestations, [0, "url"], str)
        if not attestation_url:
            logger.debug("No attestation reported for %s", purl)
            return None, None, False

        attestation_data = send_get_http(attestation_url, headers={})
        if not attestation_data:
            return None, None, False

        return (
            PyPIRegistry().extract_attestation(attestation_data),
            attestation_url,
            json_extract(result_attestations, [0, "verified"], bool) or False,
        )

    @staticmethod
    def extract_links(json_data: dict) -> tuple[list[str], RepoFinderInfo]:
        """
        Extract the repository links from  the deps.dev json data.

        Parameters
        ----------
        json_data : dict
            The json metadata.

        Returns
        -------
        tuple[list[str], RepoFinderOutcome] :
            The extracted contents as a list, and the outcome to report.
        """
        links_keys = ["version", "links"] if "version" in json_data else ["links"]
        links = json_extract(json_data, links_keys, list)
        if not links:
            logger.debug("Could not extract 'version' or 'links' from deps.dev response.")
            return [], RepoFinderInfo.DDEV_JSON_INVALID

        result = []
        for item in links:
            url = item.get("url")
            if url and isinstance(url, str):
                result.append(url)

        if not result:
            logger.debug("No str entries in 'links' list.")
            return [], RepoFinderInfo.DDEV_NO_URLS

        return result, RepoFinderInfo.FOUND
