# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The module provides abstractions for the pypi package registry."""

import logging
import os
import urllib.parse
from datetime import datetime

import requests
from bs4 import BeautifulSoup, Tag

from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError, InvalidHTTPResponseError
from macaron.json_tools import json_extract
from macaron.malware_analyzer.datetime_parser import parse_datetime
from macaron.slsa_analyzer.build_tool import Pip, Poetry
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.package_registry.package_registry import PackageRegistry
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class PyPIRegistry(PackageRegistry):
    """This class implements the pypi package registry."""

    def __init__(
        self,
        registry_url_netloc: str | None = None,
        registry_url_scheme: str | None = None,
        fileserver_url_netloc: str | None = None,
        fileserver_url_scheme: str | None = None,
        request_timeout: int | None = None,
        enabled: bool = True,
    ) -> None:
        """
        Initialize the pypi Registry instance.

        Parameters
        ----------
        registry_url_netloc: str | None
            The netloc of the pypi registry url.
        registry_url_scheme: str | None
            The scheme of the pypi registry url.
        fileserver_url_netloc: str | None
            The netloc of the server url that stores package source files, which contains the hostname and port.
        fileserver_url_scheme: str | None
            The scheme of the server url that stores package source files.
        request_timeout: int | None
            The timeout (in seconds) for requests made to the package registry.
        enabled: bool
            Shows whether making REST API calls to pypi registry is enabled.

        """
        self.registry_url_netloc = registry_url_netloc or ""
        self.registry_url_scheme = registry_url_scheme or ""
        self.fileserver_url_netloc = fileserver_url_netloc or ""
        self.fileserver_url_scheme = fileserver_url_scheme or ""
        self.request_timeout = request_timeout or 10
        self.enabled = enabled
        self.attestation: dict = {}
        self.registry_url = ""
        self.package = ""
        super().__init__("PyPI Registry")

    def load_defaults(self) -> None:
        """Load the .ini configuration for the current package registry.

        Raises
        ------
        ConfigurationError
            If there is a schema violation in the ``pypi`` section.
        """
        section_name = "package_registry.pypi"
        if not defaults.has_section(section_name):
            return
        section = defaults[section_name]

        self.registry_url_netloc = section.get("registry_url_netloc")
        if not self.registry_url_netloc:
            raise ConfigurationError(
                f'The "registry_url_netloc" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        self.registry_url_scheme = section.get("registry_url_scheme", "https")
        self.registry_url = urllib.parse.ParseResult(
            scheme=self.registry_url_scheme,
            netloc=self.registry_url_netloc,
            path="",
            params="",
            query="",
            fragment="",
        ).geturl()

        fileserver_url_netloc = section.get("fileserver_url_netloc")
        if not fileserver_url_netloc:
            raise ConfigurationError(
                f'The "fileserver_url_netloc" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        self.fileserver_url_netloc = fileserver_url_netloc
        self.fileserver_url_scheme = section.get("fileserver_url_scheme", "https")

        try:
            self.request_timeout = section.getint("request_timeout", fallback=10)
        except ValueError as error:
            raise ConfigurationError(
                f'The "request_timeout" value in section [{section_name}]'
                f"of the .ini configuration file is invalid: {error}",
            ) from error

    def is_detected(self, build_tool: BaseBuildTool) -> bool:
        """Detect if artifacts of the repo under analysis can possibly be published to this package registry.

        The detection here is based on the repo's detected build tools.
        If the package registry is compatible with the given build tools, it can be a
        possible place where the artifacts produced from the repo are published.

        ``PyPIRegistry`` is compatible with Pip and Poetry.

        Parameters
        ----------
        build_tool: BaseBuildTool
            A detected build tool of the repository under analysis.

        Returns
        -------
        bool
            ``True`` if the repo under analysis can be published to this package registry,
            based on the given build tool.
        """
        compatible_build_tool_classes = [Pip, Poetry]
        for build_tool_class in compatible_build_tool_classes:
            if isinstance(build_tool, build_tool_class):
                return True
        return False

    def download_attestation_payload(self, package: str) -> bool:
        """Download the pypi attestation from pypi registry.

        Parameters
        ----------
        package: str
            The package name.

        Returns
        -------
        bool
            ``True`` if the asset is downloaded successfully; ``False`` if not.

        Raises
        ------
        InvalidHTTPResponseError
            If the HTTP request to the registry fails or an unexpected response is returned.
        """
        self.package = package
        attestation_endpoint = f"pypi/{package}/json"
        url = urllib.parse.urljoin(self.registry_url, attestation_endpoint)
        response = send_get_http_raw(url, headers=None, timeout=self.request_timeout)

        if not response:
            logger.debug("Unable to find attestation for %s", package)
            return False

        try:
            res_obj = response.json()
        except requests.exceptions.JSONDecodeError as error:
            raise InvalidHTTPResponseError(f"Failed to process response from pypi for {url}.") from error
        if not res_obj:
            raise InvalidHTTPResponseError(f"Empty response returned by {url} .")
        self.attestation = res_obj

        return True

    def get_releases(self) -> dict | None:
        """Get all releases.

        Returns
        -------
        dict | None
            Version to metadata.
        """
        return json_extract(self.attestation, ["releases"], dict)

    def get_project_links(self) -> dict | None:
        """Retrieve the project links from the base metadata.

        This method accesses the "info" section of the base metadata to extract the "project_urls" dictionary,
        which contains various links related to the project.

        Returns
        -------
        dict | None
            Containing project URLs where the keys are the names of the links
            and the values are the corresponding URLs. Returns None if the "project_urls"
            section is not found in the base metadata.
        """
        return json_extract(self.attestation, ["info", "project_urls"], dict)

    def get_latest_version(self) -> str | None:
        """Get the latest version of the package.

        Returns
        -------
        str | None
            The latest version.
        """
        return json_extract(self.attestation, ["info", "version"], str)

    def get_sourcecode_url(self) -> str | None:
        """Get the url of the source distribution.

        Returns
        -------
        str | None
            The URL of the source distribution.
        """
        urls: list | None = json_extract(self.attestation, ["urls"], list)
        if not urls:
            return None
        for distribution in urls:
            if distribution.get("python_version") != "source":
                continue
            source_url: str = distribution.get("url", "")
            if source_url:
                parsed_url = urllib.parse.urlparse(source_url)
                if self.fileserver_url_netloc and self.fileserver_url_scheme:
                    return urllib.parse.ParseResult(
                        scheme=self.fileserver_url_scheme,
                        netloc=self.fileserver_url_netloc,
                        path=parsed_url.path,
                        params="",
                        query="",
                        fragment="",
                    ).geturl()
        return None

    def get_latest_release_upload_time(self) -> str | None:
        """Get upload time of the latest release.

        Returns
        -------
        str | None
            The upload time of the latest release.
        """
        urls: list | None = json_extract(self.attestation, ["urls"], list)
        if urls is not None and urls:
            upload_time: str | None = urls[0].get("upload_time")
            return upload_time
        return None

    def get_package_page(self) -> str | None:
        """Implement custom API to get package main page.

        Returns
        -------
        str | None
            The package main page.
        """
        url = os.path.join(self.registry_url, "project", self.package)
        response = send_get_http_raw(url)
        if response:
            html_snippets = response.content.decode("utf-8")
            return html_snippets
        return None

    def get_maintainers_of_package(self) -> list | None:
        """Implement custom API to get all maintainers of the package.

        Returns
        -------
        list | None
            The list of maintainers.
        """
        package_page: str | None = self.get_package_page()
        if package_page is None:
            return None
        soup = BeautifulSoup(package_page, "html.parser")
        maintainers = soup.find_all("span", class_="sidebar-section__user-gravatar-text")
        return list({maintainer.get_text(strip=True) for maintainer in maintainers})

    def get_maintainer_profile_page(self, username: str) -> str | None:
        """Implement custom API to get maintainer's profile page.

        Parameters
        ----------
        username: str
            The maintainer's username.

        Returns
        -------
        str | None
            The profile page.
        """
        url = os.path.join(self.registry_url, "user", username)
        response = send_get_http_raw(url, headers=None)
        if response:
            html_snippets = response.content.decode("utf-8")
            return html_snippets
        return None

    def get_maintainer_join_date(self, username: str) -> datetime | None:
        """Implement custom API to get the maintainer's join date.

        Parameters
        ----------
        username: str
            The maintainer's username.

        Returns
        -------
            datetime | None: Maintainers join date. Only recent maintainer's data available.
        """
        user_page: str | None = self.get_maintainer_profile_page(username)
        if user_page is None:
            return None

        soup = BeautifulSoup(user_page, "html.parser")
        span = soup.find("span", class_="sr-only", string="Date joined")
        if not span:
            return None

        next_element = span.find_next("time")
        # Loop to skip over any NavigableString instances.
        while next_element and not isinstance(next_element, Tag):
            next_element = next_element.find_next()

        if not next_element:
            return None

        if next_element.name != "time" or "datetime" not in next_element.attrs:
            return None

        datetime_val = next_element["datetime"]

        if not isinstance(datetime_val, str):
            return None

        # Define the format of the datetime string.
        datetime_format = "%Y-%m-%dT%H:%M:%S%z"
        # Return the parsed string to a datetime object.
        res: datetime | None = parse_datetime(datetime_val, datetime_format)

        return res.replace(tzinfo=None) if res else None
