# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines package registries."""

import json
import logging
import urllib.parse
from abc import ABC, abstractmethod
from datetime import datetime
from urllib.parse import quote as encode

import requests

from macaron.errors import InvalidHTTPResponseError
from macaron.json_tools import json_extract
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class PackageRegistry(ABC):
    """Base package registry class."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def load_defaults(self) -> None:
        """Load the .ini configuration for the current package registry."""

    @abstractmethod
    def is_detected(self, build_tool: BaseBuildTool) -> bool:
        """Detect if artifacts of the repo under analysis can possibly be published to this package registry.

        The detection here is based on the repo's detected build tool.
        If the package registry is compatible with the given build tool, it can be a
        possible place where the artifacts produced from the repo are published.

        Parameters
        ----------
        build_tool : BaseBuildTool
            A detected build tool of the repository under analysis.

        Returns
        -------
        bool
            ``True`` if the repo under analysis can be published to this package registry,
            based on the given build tool.
        """

    def find_publish_timestamp(self, purl: str, registry_url: str | None = None) -> datetime:
        """Retrieve the publication timestamp for a package specified by its purl from the deps.dev repository by default.

        This method constructs a request URL based on the provided purl, sends an HTTP GET
        request to fetch metadata about the package, and extracts the publication timestamp
        from the response.

        Note: The method expects the response to include a ``version`` field with a ``publishedAt``
        subfield containing an ISO 8601 formatted timestamp.

        Parameters
        ----------
        purl: str
            The Package URL (purl) of the package whose publication timestamp is to be retrieved.
            This should conform to the PURL specification.
        registry_url: str | None
            The registry URL that can be set for testing.

        Returns
        -------
        datetime
            A timezone-aware datetime object representing the publication timestamp
            of the specified package.

        Raises
        ------
        InvalidHTTPResponseError
            If the URL construction fails, the HTTP response is invalid, or if the response
            cannot be parsed correctly, or if the expected timestamp is missing or invalid.
        NotImplementedError
            If not implemented for a registry.
        """
        # TODO: To reduce redundant calls to deps.dev, store relevant parts of the response
        # in the AnalyzeContext object retrieved by the Repo Finder. This step should be
        # implemented at the beginning of the analyze command to ensure that the data
        # is available for subsequent processing.

        base_url_parsed = urllib.parse.urlparse(registry_url or "https://api.deps.dev")
        path_params = "/".join(["v3alpha", "purl", encode(purl).replace("/", "%2F")])
        try:
            url = urllib.parse.urlunsplit(
                urllib.parse.SplitResult(
                    scheme=base_url_parsed.scheme,
                    netloc=base_url_parsed.netloc,
                    path=path_params,
                    query="",
                    fragment="",
                )
            )
        except ValueError as error:
            raise InvalidHTTPResponseError("Failed to construct the API URL.") from error

        response = send_get_http_raw(url)
        if response and response.text and response.status_code == 200:
            try:
                metadata: dict = json.loads(response.text)
            except requests.exceptions.JSONDecodeError as error:
                raise InvalidHTTPResponseError(f"Failed to process response from deps.dev for {url}.") from error
            if not metadata:
                raise InvalidHTTPResponseError(f"Empty response returned by {url} .")

            timestamp = json_extract(metadata, ["version", "publishedAt"], str)
            if not timestamp:
                raise InvalidHTTPResponseError(f"The timestamp is missing in the response returned by {url}.")

            logger.debug("Found timestamp: %s.", timestamp)

            try:
                return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (OverflowError, OSError) as error:
                raise InvalidHTTPResponseError(f"The timestamp returned by {url} is invalid") from error

        raise InvalidHTTPResponseError(f"Invalid response from deps.dev for {url}.")
