# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the PythonRepoFinderDD class to be used for finding repositories using deps.dev."""
import json
import logging
from collections.abc import Iterator
from urllib.parse import quote as encode

import requests

from macaron.repo_finder.repo_finder_base import BaseRepoFinder

logger: logging.Logger = logging.getLogger(__name__)


class RepoFinderDD(BaseRepoFinder):
    """This class is used to find repositories using Google's Open Source Insights tool (deps.dev)."""

    # The label used by deps.dev to denote repository urls (Based on observation ONLY)
    repo_url_label = "SOURCE_REPO"

    def __init__(self, purl_type: str) -> None:
        """Initialise the deps.dev repository finder instance.

        Parameters
        ----------
        purl_type : str
            The PURL type this instance is intended for use with.
        """
        self.type = purl_type

    def find_repo(self, group: str, artifact: str, version: str) -> Iterator[str]:
        """
        Attempt to retrieve a repository URL that matches the passed artifact.

        Parameters
        ----------
        group : str
            The group identifier of an artifact.
        artifact : str
            The artifact name of an artifact.
        version : str
            The version number of an artifact.

        Yields
        ------
        Iterator[str] :
            The URLs found for the passed GAV.
        """
        request_urls = self.create_urls(group, artifact, version)
        if not request_urls:
            logger.debug("No urls found for: %s", artifact)
            return

        with requests.Session() as session:
            metadata = self.retrieve_metadata(session, request_urls[0])
            if not metadata:
                logger.debug("Failed to retrieve metadata for: %s", artifact)
                return

        urls, url_count = self.read_metadata(metadata)
        if url_count == 0:
            logger.debug("Failed to extract repository URLs from metadata: %s", artifact)
            return

        yield from urls

    def create_urls(self, group: str, artifact: str, version: str) -> list[str]:
        """
        Create the urls to search for the metadata relating to the passed artifact.

        If a version is not specified, remote API calls will be used to try and find one.

        Parameters
        ----------
        group : str
            The group ID.
        artifact: str
            The artifact ID.
        version: str
            The version of the artifact.

        Returns
        -------
        list[str]
            The list of created URLs.
        """
        package_name = f"{group}:{artifact}:{version}"
        base_url = self.create_type_specific_url(group, artifact)

        if version:
            return [f"{base_url}/versions/{version}"]

        # Find the latest version.
        with requests.Session() as session:
            try:
                result = session.get(base_url)
            except (requests.RequestException, OSError) as error:
                logger.debug("Error during version retrieval: %s", error)
                return []

            if not result.ok:
                logger.debug("Failed to retrieve versions for: %s, error code: %s", package_name, result.status_code)
                return []

        metadata = json.loads(result.text)
        versions = metadata["versions"]
        latest_version = versions[len(version) - 1]["versionKey"]["version"]

        if latest_version:
            return [f"{base_url}/versions/{latest_version}"]

        return []

    def retrieve_metadata(self, session: requests.Session, url: str) -> str:
        """
        Attempt to retrieve the file located at the passed URL using the passed Session.

        Parameters
        ----------
        session : requests.Session
            The HTTP session to use for attempting the GET request.
        url : str
            The URL for the GET request.

        Returns
        -------
        str :
            The retrieved file data or an empty string.
        """
        try:
            result = session.get(url)
        except (requests.RequestException, OSError) as error:
            logger.debug("Error during metadata retrieval: %s", error)
            return ""

        if not result.ok:
            logger.debug("Failed to retrieve metadata at: %s, error code: %s", url, result.status_code)
            return ""

        return result.text

    def read_metadata(self, metadata: str) -> tuple[Iterator[str], int]:
        """
        Parse the deps.dev metadata and extract the repository links.

        Parameters
        ----------
        metadata : str
            The metadata as a string.

        Returns
        -------
        tuple[Iterator[str], int] :
            The extracted contents in iterable form and count as a tuple.
        """
        parsed = json.loads(metadata)

        if not parsed["links"]:
            logger.debug("Metadata had no URLs: %s", parsed["versionKey"])
            return iter([]), 0

        for link in parsed["links"]:
            if link["label"] == self.repo_url_label:
                return iter([link["url"]]), 1

        return iter([]), 0

    def create_type_specific_url(self, namespace: str, name: str) -> str:
        """Create a url for the deps.dev API based on the package type.

        Parameters
        ----------
        namespace : str
            The PURL namespace element.
        name : str
            The PURL name element.

        Returns
        -------
        str :
            The specific URL relating to the package.
        """
        namespace = encode(namespace)
        name = encode(name)

        match self.type:
            case "pypi":
                package_name = name.lower().replace("_", "-")
            case "npm":
                if namespace:
                    package_name = f"%40{namespace}%2F{name}"
                else:
                    package_name = name
            case "nuget" | "cargo":
                package_name = name

            case _:
                logger.debug("PURL type not yet supported: %s", self.type)
                return ""

        return f"https://api.deps.dev/v3alpha/systems/{self.type}/packages/{package_name}"
