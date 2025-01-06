# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains implementation of deps.dev service."""

import json
import logging
import urllib.parse
from json.decoder import JSONDecodeError
from urllib.parse import quote as encode

from macaron.config.defaults import defaults
from macaron.errors import APIAccessError
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class DepsDevService:
    """The deps.dev service class."""

    @staticmethod
    def get_package_info(purl: str) -> dict | None:
        """Check if the package identified by the PackageURL (PURL) exists and return its information.

        Parameters
        ----------
        purl: str
            The PackageURL (PURL).

        Returns
        -------
        dict | None
            The package metadata or None if it doesn't exist.

        Raises
        ------
        APIAccessError
            If the service is misconfigured, the API is invalid, a network error happens,
            or unexpected response is returned by the API.
        """
        section_name = "deps_dev"
        if not defaults.has_section(section_name):
            return None
        section = defaults[section_name]

        url_netloc = section.get("url_netloc")
        if not url_netloc:
            raise APIAccessError(
                f'The "url_netloc" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        url_scheme = section.get("url_scheme", "https")
        purl_endpoint = section.get("purl_endpoint")
        if not purl_endpoint:
            raise APIAccessError(
                f'The "purl_endpoint" key is missing in section [{section_name}] of the .ini configuration file.'
            )

        path_params = "/".join([purl_endpoint, encode(purl, safe="")])
        try:
            url = urllib.parse.urlunsplit(
                urllib.parse.SplitResult(
                    scheme=url_scheme,
                    netloc=url_netloc,
                    path=path_params,
                    query="",
                    fragment="",
                )
            )
        except ValueError as error:
            raise APIAccessError("Failed to construct the API URL.") from error

        response = send_get_http_raw(url)
        if response and response.text:
            try:
                metadata: dict = json.loads(response.text)
            except JSONDecodeError as error:
                raise APIAccessError(f"Failed to process response from deps.dev for {url}.") from error
            if not metadata:
                raise APIAccessError(f"Empty response returned by {url} .")
            return metadata

        return None
