# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the PythonRepoFinderDD class to be used for finding repositories using deps.dev."""
import json
import logging
from urllib.parse import quote as encode

from packageurl import PackageURL

from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_validator import find_valid_repository_url
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)

# This list should be updated based on updates to deps.dev.
SUPPORTED_TYPES = ["maven", "pypi", "nuget", "cargo", "npm"]


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
        request_urls = self._create_urls(purl.namespace or "", purl.name, purl.version or "", purl.type)
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

    def _create_urls(self, namespace: str, name: str, version: str, type_: str) -> list[str]:
        """
        Create the urls to search for the metadata relating to the passed artifact.

        If a version is not specified, remote API calls will be used to try and find one.

        Parameters
        ----------
        namespace : str
            The PURL namespace.
        name: str
            The PURL name.
        version: str
            The PURL version.
        type : str
            The PURL type.

        Returns
        -------
        list[str]
            The list of created URLs.
        """
        base_url = self._create_type_specific_url(namespace, name, type_)

        if not base_url:
            return []

        if version:
            return [f"{base_url}/versions/{version}"]

        # Find the latest version.
        response = send_get_http_raw(base_url, {})

        if not response:
            return []

        metadata = json.loads(response.text)
        versions = metadata["versions"]
        latest_version = versions[len(version) - 1]["versionKey"]["version"]

        if latest_version:
            logger.debug("Found latest version: %s", latest_version)
            return [f"{base_url}/versions/{latest_version}"]

        return []

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
        parsed = json.loads(json_data)

        if not parsed["links"]:
            logger.debug("Metadata had no URLs: %s", parsed["versionKey"])
            return []

        result = []
        for item in parsed["links"]:
            result.append(item.get("url"))

        return result

    def _create_type_specific_url(self, namespace: str, name: str, type_: str) -> str:
        """Create a URL for the deps.dev API based on the package type.

        Parameters
        ----------
        namespace : str
            The PURL namespace element.
        name : str
            The PURL name element.
        type : str
            The PURL type.

        Returns
        -------
        str :
            The specific URL relating to the package.
        """
        namespace = encode(namespace)
        name = encode(name)

        # See https://docs.deps.dev/api/v3alpha/
        match type_:
            case "pypi":
                package_name = name.lower().replace("_", "-")
            case "npm":
                if namespace:
                    package_name = f"{namespace}%2F{name}"
                else:
                    package_name = name
            case "nuget" | "cargo":
                package_name = name
            case "maven":
                package_name = f"{namespace}%3A{name}"

            case _:
                logger.debug("PURL type not yet supported: %s", type_)
                return ""

        return f"https://api.deps.dev/v3alpha/systems/{type_}/packages/{package_name}"
