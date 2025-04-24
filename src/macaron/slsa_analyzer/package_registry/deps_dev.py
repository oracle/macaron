# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains implementation of deps.dev service."""

import json
import logging
import urllib.parse
from json.decoder import JSONDecodeError
from typing import Any
from urllib.parse import quote as encode
from urllib.parse import unquote as decode

from macaron.config.defaults import defaults
from macaron.errors import APIAccessError
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class DepsDevService:
    """The deps.dev service class."""

    @staticmethod
    def get_endpoint(purl: bool = True, path: str | None = None) -> Any:
        """Build the API endpoint for the deps.dev service and return it.

        Parameters
        ----------
        purl: bool
            A flag to determine whether the PURL or BASE endpoint should be returned.
        path: str | None
            A path to be added to the URL.

        Returns
        -------
        Any
            The API endpoint.
        """
        section_name = "deps_dev"
        if not defaults.has_section(section_name):
            raise APIAccessError(f"The {section_name} section is missing in the .ini configuration file.")
        section = defaults[section_name]

        url_netloc = section.get("url_netloc")
        if not url_netloc:
            raise APIAccessError(
                f'The "url_netloc" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        url_scheme = section.get("url_scheme", "https")

        api_endpoint = section.get("api_endpoint")
        if not api_endpoint:
            raise APIAccessError(
                f'The "api_endpoint" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        endpoint_path = [api_endpoint]
        if path:
            endpoint_path.append(path)
        if not purl:
            try:
                return urllib.parse.SplitResult(
                    scheme=url_scheme,
                    netloc=url_netloc,
                    path="/".join(endpoint_path),
                    query="",
                    fragment="",
                )
            except ValueError as error:
                raise APIAccessError("Failed to construct the API URL.") from error

        purl_endpoint = section.get("purl_endpoint")
        if not purl_endpoint:
            raise APIAccessError(
                f'The "purl_endpoint" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        endpoint_path.insert(1, purl_endpoint)
        try:
            return urllib.parse.SplitResult(
                scheme=url_scheme,
                netloc=url_netloc,
                path="/".join(endpoint_path),
                query="",
                fragment="",
            )
        except ValueError as error:
            raise APIAccessError("Failed to construct the API URL.") from error

    @staticmethod
    def get_package_info(purl: str) -> dict:
        """Check if the package identified by the PackageURL (PURL) exists and return its information.

        Parameters
        ----------
        purl: str
            The PackageURL (PURL).

        Returns
        -------
        dict
            The package metadata.

        Raises
        ------
        APIAccessError
            If the service is misconfigured, the API is invalid, a network error happens,
            or unexpected response is returned by the API.
        """
        if "%" in purl:
            purl = decode(purl)
        purl = encode(purl, safe="")

        api_endpoint = DepsDevService.get_endpoint(path=purl)
        url = urllib.parse.urlunsplit(api_endpoint)

        response = send_get_http_raw(url)
        if response and response.text:
            try:
                metadata: dict = json.loads(response.text)
                return metadata
            except JSONDecodeError as error:
                raise APIAccessError(f"Failed to process response from deps.dev for {url}.") from error

        raise APIAccessError(f"No valid response from deps.dev for {url}")
