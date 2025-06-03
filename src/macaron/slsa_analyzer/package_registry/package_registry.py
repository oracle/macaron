# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines package registries."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime

from macaron.errors import APIAccessError, InvalidHTTPResponseError
from macaron.json_tools import json_extract
from macaron.slsa_analyzer.package_registry.deps_dev import DepsDevService

logger: logging.Logger = logging.getLogger(__name__)


class PackageRegistry(ABC):
    """Base package registry class."""

    def __init__(self, name: str, build_tool_names: set[str]) -> None:
        self.name = name
        self.build_tool_names = build_tool_names
        self.enabled: bool = True

    @abstractmethod
    def load_defaults(self) -> None:
        """Load the .ini configuration for the current package registry."""

    def is_detected(self, build_tool_name: str) -> bool:
        """Detect if artifacts of the repo under analysis can possibly be published to this package registry.

        The detection here is based on the repo's detected build tool.
        If the package registry is compatible with the given build tool, it can be a
        possible place where the artifacts produced from the repo are published.

        Parameters
        ----------
        build_tool_name: str
            The name of a detected build tool of the repository under analysis.

        Returns
        -------
        bool
            ``True`` if the repo under analysis can be published to this package registry,
            based on the given build tool.
        """
        if not self.enabled:
            return False
        return build_tool_name in self.build_tool_names

    def find_publish_timestamp(self, purl: str) -> datetime:
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
        try:
            metadata = DepsDevService.get_package_info(purl)
        except APIAccessError as error:
            raise InvalidHTTPResponseError(f"Invalid response from deps.dev for {purl}.") from error
        if metadata:
            timestamp = json_extract(metadata, ["version", "publishedAt"], str)
            if not timestamp:
                raise InvalidHTTPResponseError(f"The timestamp is missing in the response returned for {purl}.")

            logger.debug("Found timestamp: %s.", timestamp)

            try:
                return datetime.fromisoformat(timestamp)
            except ValueError as error:
                raise InvalidHTTPResponseError(f"The timestamp returned for {purl} is invalid") from error

        raise InvalidHTTPResponseError(f"Invalid response from deps.dev for {purl}.")
