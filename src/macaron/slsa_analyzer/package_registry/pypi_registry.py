# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The module provides abstractions for the pypi package registry."""

import logging
import os
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from macaron.slsa_analyzer.package_registry.package_registry import PackageRegistry
from macaron.util import send_get_http, send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class PyPIRegistry(PackageRegistry):
    """This class implements the npm package registry.

    There is no complete and up-to-date API documentation for the npm registry and the endpoints
    are discovered by manual inspection of links on https://www.npmjs.com.
    """

    def __init__(
        self,
        hostname: str | None = None,
        attestation_endpoint: str | None = None,
        request_timeout: int | None = None,
        enabled: bool = True,
    ) -> None:
        """
        Initialize the npm Registry instance.

        Parameters
        ----------
        hostname : str | None
            The hostname of the npm registry.
        attestation_endpoint : str | None
            The attestation REST API.
        request_timeout : int | None
            The timeout (in seconds) for requests made to the package registry.
        enabled: bool
            Shows whether making REST API calls to npm registry is enabled.
        """
        self.hostname = hostname or ""
        self.attestation_endpoint = attestation_endpoint or ""
        self.request_timeout = request_timeout or 10
        self.enabled = enabled
        super().__init__("pypi Registry")


class PyPIApiClient:
    """PyPI's official and customed API client."""

    def __init__(self, package: str) -> None:
        self.headers = {"Host": "pypi.org", "Accept": "application/json"}
        self.base_url = "https://pypi.org"
        self.package = package
        self.base_metadata: dict[str, Any] = self._get_base_metadata()

    def _get_base_metadata(self) -> dict:
        """Get the metadata through PyPI official API.

        Returns
        -------
            dict | None: PyPI official metadata.
        """
        endpoint = os.path.join(self.base_url, "pypi", self.package, "json")
        response: dict = send_get_http(endpoint, headers=self.headers)
        return response

    def get_releases(self) -> dict | None:
        """Get all releases.

        Returns
        -------
            dict | None: Version to metadata.
        """
        releases: dict | None = self.base_metadata.get("releases", None)
        return releases

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
        project_urls: dict[str, str] | None = self.base_metadata.get("info", None).get("project_urls", None)
        return project_urls

    def get_latest_version(self) -> str | None:
        """Get latest version of the package.

        Returns
        -------
            str | None: Latest version.
        """
        version: str | None = self.base_metadata.get("info", None).get("version", None)
        return version

    def get_sourcecode_url(self) -> str | None:
        """Get the url of the source distribution.

        Returns
        -------
            str | None: Url of the source distribution.
        """
        for distribution in self.base_metadata.get("urls", []):
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
        distributions = self.base_metadata.get("urls", None)
        return distributions[0].get("upload_time") if distributions is not None else None

    def get_package_page(self) -> str | None:
        """Implement custom API to get package main page.

        Returns
        -------
            str | None: Package main page.
        """
        url = os.path.join(self.base_url, "project", self.package)
        response = send_get_http_raw(url, headers=self.headers)
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
        response = send_get_http_raw(url, headers=self.headers)
        if response:
            html_snippets = response.content.decode("utf-8")
            return html_snippets
        return None

    def get_maintainer_join_date(self, maintainer: str) -> datetime | None:
        """Implement custom API to get the maintainers join date.

        Parameters
        ----------
            maintainer (_type_): Username.

        Returns
        -------
            datetime | None: Maintainers join date. Only recent maintainer's data available.
        """
        user_page: str | None = self.get_maintainer_profile_page(maintainer)
        if user_page:
            pattern = r'Joined <time datetime="([^"]+)"'
            match = re.search(pattern, user_page)
            # Check if a match is found
            if match:
                # Extract the matched timestamp
                datetime_str = match.group(1)
                # Define the format of the datetime string
                datetime_format = "%Y-%m-%dT%H:%M:%S%z"
                # Return the parsed string to a datetime object
                return datetime.strptime(datetime_str, datetime_format).replace(tzinfo=None)
        return None
