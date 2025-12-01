# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains implementation of deps.dev service."""

import json
import logging
import urllib.parse
from json.decoder import JSONDecodeError

from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.errors import APIAccessError
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class DepsDevService:
    """The deps.dev service class."""

    @staticmethod
    def get_purl_endpoint(purl: PackageURL | str) -> urllib.parse.SplitResult:
        """Build the purl API endpoint for the deps.dev service and return it.

        Parameters
        ----------
        purl: PackageURL | str
            The PURL to append to the API endpoint.

        Returns
        -------
        urllib.parse.SplitResult
            The purl API endpoint.

        Raises
        ------
        APIAccessError
            If building the API endpoint fails.
        """
        encoded_purl = DepsDevService.encode_purl(purl)
        if not encoded_purl:
            raise APIAccessError("The PURL could not be encoded.")

        purl_endpoint = defaults.get("deps_dev", "purl_endpoint", fallback="")
        if not purl_endpoint:
            raise APIAccessError(
                'The "purl_endpoint" key is missing in section [deps_dev] of the .ini configuration file.'
            )

        base_url = DepsDevService.get_endpoint()

        try:
            return urllib.parse.SplitResult(
                scheme=base_url.scheme,
                netloc=base_url.netloc,
                path="/".join([base_url.path, purl_endpoint, encoded_purl]),
                query="",
                fragment="",
            )
        except ValueError as error:
            raise APIAccessError("Failed to construct the PURL API URL.") from error

    @staticmethod
    def get_endpoint(path: str | None = None) -> urllib.parse.SplitResult:
        """Build the API endpoint for the deps.dev service and return it.

        Parameters
        ----------
        path: str | None
            A path to be appended to the API endpoint.

        Returns
        -------
        urllib.parse.SplitResult
            The API endpoint.
        """
        section_name = "deps_dev"
        if not defaults.has_section(section_name):
            raise APIAccessError(f"The {section_name} section is missing in the .ini configuration file.")
        section = defaults[section_name]

        if not section.getboolean("enabled", fallback=True):
            raise APIAccessError("The DepsDev API is disabled in the .ini configuration file.")

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
    def encode_purl(purl: PackageURL | str) -> str | None:
        """Encode a PURL to match the deps.dev requirements.

        The fragment (subpath) and query (qualifiers) PURL sections are not accepted by deps.dev.
        See: https://docs.deps.dev/api/v3alpha/index.html#purllookup.
        The documentation claims that all special characters must be percent-encoded. This is not strictly true, as '@'
        and ':' are accepted as is. The forward slashes in the PURL must be encoded to distinguish them from URL parts.

        Parameters
        ----------
        purl: PackageURL | str
            The PURL to encode.

        Returns
        -------
        str | None
            The encoded PURL.
        """
        try:
            original_purl = purl if isinstance(purl, PackageURL) else PackageURL.from_string(purl)
            new_purl = PackageURL(
                type=original_purl.type,
                namespace=original_purl.namespace,
                name=original_purl.name,
                version=original_purl.version,
            )
        except ValueError as error:
            logger.debug(error)
            return None

        # We rely on packageurl calling urllib to encode PURLs for all special characters except forward slash: "/".
        encoded = str(new_purl).replace("/", "%2F")

        return encoded

    @staticmethod
    def get_package_info(purl: PackageURL | str) -> dict:
        """Check if the package identified by the PackageURL (PURL) exists and return its information.

        Parameters
        ----------
        purl: PackageURL | str
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
        api_endpoint = DepsDevService.get_purl_endpoint(purl)
        url = urllib.parse.urlunsplit(api_endpoint)

        response = send_get_http_raw(url)
        if response and response.text:
            try:
                metadata: dict = json.loads(response.text)
                return metadata
            except JSONDecodeError as error:
                raise APIAccessError(f"Failed to process response from deps.dev for {url}.") from error

        raise APIAccessError(f"No valid response from deps.dev for {url}")
