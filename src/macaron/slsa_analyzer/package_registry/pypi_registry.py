# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The module provides abstractions for the pypi package registry."""

import logging
import os
from datetime import datetime
from urllib.parse import urljoin

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
        hostname: str | None = None,
        attestation_endpoint: str | None = None,
        request_timeout: int | None = None,
        enabled: bool = True,
    ) -> None:
        """
        Initialize the pypi Registry instance.

        Parameters
        ----------
        hostname : str | None
            The hostname of the pypi registry.
        attestation_endpoint : str | None
            The attestation REST API.
        request_timeout : int | None
            The timeout (in seconds) for requests made to the package registry.
        enabled: bool
            Shows whether making REST API calls to pypi registry is enabled.

        """
        self.hostname = hostname or ""
        self.attestation_endpoint = attestation_endpoint or ""
        self.request_timeout = request_timeout or 10
        self.enabled = enabled
        self.attestation: dict = {}
        self.base_url = ""
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

        self.hostname = section.get("hostname")
        if not self.hostname:
            raise ConfigurationError(
                f'The "hostname" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        self.base_url = f"https://{self.hostname}"
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
        build_tool : BaseBuildTool
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
            PyPI's package name.

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
        self.attestation_endpoint = f"pypi/{package}/json"
        url = urljoin(self.base_url, self.attestation_endpoint)
        response = send_get_http_raw(url, headers=None, timeout=None)
        if not response or response.status_code != 200:
            logger.debug(
                "Unable to find attestation at %s",
            )
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
            dict | None: Version to metadata.
        """
        return json_extract(self.attestation, ["releases"], dict)

    def get_project_links(self) -> dict[str, str] | None:
        """Retrieve the project links from the base metadata.

        This method accesses the "info" section of the base metadata to extract the "project_urls" dictionary,
        which contains various links related to the project.

        Returns
        -------
            dict[str, str] | None: Containing project URLs where the keys are the names of the links
                               and the values are the corresponding URLs. Returns None if the "project_urls"
                               section is not found in the base metadata.
        """
        return json_extract(self.attestation, ["info", "project_urls"], dict)

    def get_latest_version(self) -> str | None:
        """Get latest version of the package.

        Returns
        -------
            str | None: Latest version.
        """
        return json_extract(self.attestation, ["info", "version"], str)

    def get_sourcecode_url(self) -> str | None:
        """Get the url of the source distribution.

        Returns
        -------
            str | None: Url of the source distribution.
        """
        urls: list | None = json_extract(self.attestation, ["urls"], list)
        if urls is not None:
            for distribution in urls:
                if distribution.get("python_version") == "source":
                    source: str = distribution.get("url", "")
                    if source:
                        return source
        return None

    def get_latest_release_upload_time(self) -> str | None:
        """Get upload time of the latest release.

        Returns
        -------
            str | None: Upload time of latest release.
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
            str | None: Package main page.
        """
        url = os.path.join(self.base_url, "project", self.package)
        response = send_get_http_raw(url)
        if response:
            html_snippets = response.content.decode("utf-8")
            return html_snippets
        return None

    def get_maintainer_of_package(self) -> list | None:
        """Implement custom API to get all maintainers of the package.

        Returns
        -------
            list | None: Maintainers.
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
            username (str): Maintainer's name.

        Returns
        -------
            str | None: Profile page.
        """
        url = os.path.join(self.base_url, "user", username)
        response = send_get_http_raw(url, headers=None)
        if response:
            html_snippets = response.content.decode("utf-8")
            return html_snippets
        return None

    def get_maintainer_join_date(self, maintainer: str) -> datetime | None:
        """Implement custom API to get the maintainers join date.

        Parameters
        ----------
            maintainer (str): Username.

        Returns
        -------
            datetime | None: Maintainers join date. Only recent maintainer's data available.
        """
        user_page: str | None = self.get_maintainer_profile_page(maintainer)
        if user_page is None:
            return None

        soup = BeautifulSoup(user_page, "html.parser")
        span = soup.find("span", class_="sr-only", string="Date joined")
        if span:
            next_element = span.find_next("time")
            # Loop to skip over any NavigableString instances
            while next_element and not isinstance(next_element, Tag):
                next_element = next_element.find_next()
            if isinstance(next_element, Tag) and next_element.name == "time" and "datetime" in next_element.attrs:
                datetime_val = next_element["datetime"]
            else:
                return None
            # Define the format of the datetime string
            datetime_format = "%Y-%m-%dT%H:%M:%S%z"
            # Return the parsed string to a datetime object
            if isinstance(datetime_val, str):
                res: datetime | None = parse_datetime(datetime_val, datetime_format)
                if res:
                    return res.replace(tzinfo=None)
        return None
