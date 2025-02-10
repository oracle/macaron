# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The module provides abstractions for the pypi package registry."""

import logging
import os
import tarfile
import tempfile
import urllib.parse
import zipfile
from dataclasses import dataclass
from datetime import datetime

import requests
from bs4 import BeautifulSoup, Tag
from requests import RequestException

from macaron.config.defaults import defaults
from macaron.database.table_definitions import Component
from macaron.errors import ConfigurationError, InvalidHTTPResponseError
from macaron.json_tools import json_extract
from macaron.malware_analyzer.datetime_parser import parse_datetime
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
        inspector_url_netloc: str | None = None,
        inspector_url_scheme: str | None = None,
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
        inspector_url_netloc: str | None
            The netloc of the inspector server url, which contains the hostname and port.
        inspector_url_scheme: str | None
            The scheme of the inspector server url.
        request_timeout: int | None
            The timeout (in seconds) for requests made to the package registry.
        enabled: bool
            Shows whether making REST API calls to pypi registry is enabled.

        """
        self.registry_url_netloc = registry_url_netloc or ""
        self.registry_url_scheme = registry_url_scheme or ""
        self.fileserver_url_netloc = fileserver_url_netloc or ""
        self.fileserver_url_scheme = fileserver_url_scheme or ""
        self.inspector_url_netloc = inspector_url_netloc or ""
        self.inspector_url_scheme = inspector_url_scheme or ""
        self.request_timeout = request_timeout or 10
        self.enabled = enabled
        self.registry_url = ""
        super().__init__("PyPI Registry", {"pip", "poetry"})

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

        self.registry_url_netloc = section.get("registry_url_netloc", "")
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

        fileserver_url_netloc = section.get("fileserver_url_netloc", "")
        if not fileserver_url_netloc:
            raise ConfigurationError(
                f'The "fileserver_url_netloc" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        self.fileserver_url_netloc = fileserver_url_netloc
        self.fileserver_url_scheme = section.get("fileserver_url_scheme", "https")

        inspector_url_netloc = section.get("inspector_url_netloc")
        if not inspector_url_netloc:
            raise ConfigurationError(
                f'The "inspector_url_netloc" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        self.inspector_url_netloc = inspector_url_netloc
        self.inspector_url_scheme = section.get("inspector_url_scheme", "https")

        try:
            self.request_timeout = section.getint("request_timeout", fallback=10)
        except ValueError as error:
            raise ConfigurationError(
                f'The "request_timeout" value in section [{section_name}]'
                f"of the .ini configuration file is invalid: {error}",
            ) from error

    def download_package_json(self, url: str) -> dict:
        """Download the package JSON metadata from pypi registry.

        Parameters
        ----------
        url: str
            The package JSON url.

        Returns
        -------
        dict
            The JSON response if the request is successful.

        Raises
        ------
        InvalidHTTPResponseError
            If the HTTP request to the registry fails or an unexpected response is returned.
        """
        response = send_get_http_raw(url, headers=None, timeout=self.request_timeout)

        if not response:
            logger.debug("Unable to find package JSON metadata using URL: %s", url)
            raise InvalidHTTPResponseError(f"Unable to find package JSON metadata using URL: {url}.")

        try:
            res_obj = response.json()
        except requests.exceptions.JSONDecodeError as error:
            raise InvalidHTTPResponseError(f"Failed to process response from pypi for {url}.") from error
        if not isinstance(res_obj, dict):
            raise InvalidHTTPResponseError(f"Empty response returned by {url} .")

        return res_obj

    def fetch_sourcecode(self, src_url: str) -> dict[str, str] | None:
        """Get the source code of the package.

        Returns
        -------
        str | None
            The source code.
        """
        # Get name of file.
        _, _, file_name = src_url.rpartition("/")

        # Create a temporary directory to store the downloaded source.
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                response = requests.get(src_url, stream=True, timeout=40)
                response.raise_for_status()
            except requests.exceptions.HTTPError as http_err:
                logger.debug("HTTP error occurred: %s", http_err)
                return None

            if response.status_code != 200:
                return None

            source_file = os.path.join(temp_dir, file_name)
            with open(source_file, "wb") as file:
                try:
                    for chunk in response.iter_content():
                        file.write(chunk)
                except RequestException as error:
                    # Something went wrong with the request, abort.
                    logger.debug("Error while streaming source file: %s", error)
                    response.close()
                    return None
            logger.debug("Begin fetching the source code from PyPI")
            py_files_content: dict[str, str] = {}
            if tarfile.is_tarfile(source_file):
                try:
                    with tarfile.open(source_file, "r:gz") as tar:
                        for member in tar.getmembers():
                            if member.isfile() and member.name.endswith(".py") and member.size > 0:
                                file_obj = tar.extractfile(member)
                                if file_obj:
                                    content = file_obj.read().decode("utf-8")
                                    py_files_content[member.name] = content
                except tarfile.ReadError as exception:
                    logger.debug("Error reading tar file: %s", exception)
                    return None
            elif zipfile.is_zipfile(source_file):
                try:
                    with zipfile.ZipFile(source_file, "r") as zip_ref:
                        for info in zip_ref.infolist():
                            if info.filename.endswith(".py") and not info.is_dir() and info.file_size > 0:
                                with zip_ref.open(info) as file_obj:
                                    content = file_obj.read().decode("utf-8")
                                    py_files_content[info.filename] = content
                except zipfile.BadZipFile as bad_zip_exception:
                    logger.debug("Error reading zip file: %s", bad_zip_exception)
                    return None
                except zipfile.LargeZipFile as large_zip_exception:
                    logger.debug("Zip file too large to read: %s", large_zip_exception)
                    return None
                # except KeyError as zip_key_exception:
                #     logger.debug(
                #         "Error finding target '%s' in zip file '%s': %s", archive_target, source_file, zip_key_exception
                #     )
                #     return None
            else:
                logger.debug("Unable to extract file: %s", file_name)

            logger.debug("Successfully fetch the source code from PyPI")
            return py_files_content

    def get_package_page(self, package_name: str) -> str | None:
        """Implement custom API to get package main page.

        Parameters
        ----------
        package_name: str
            The package name.

        Returns
        -------
        str | None
            The package main page.
        """
        url = os.path.join(self.registry_url, "project", package_name)
        response = send_get_http_raw(url)
        if response:
            html_snippets = response.content.decode("utf-8")
            return html_snippets
        return None

    def get_maintainers_of_package(self, package_name: str) -> list | None:
        """Implement custom API to get all maintainers of the package.

        Parameters
        ----------
        package_name: str
            The package name.

        Returns
        -------
        list | None
            The list of maintainers.
        """
        package_page: str | None = self.get_package_page(package_name)
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


@dataclass
class PyPIPackageJsonAsset:
    """The package JSON hosted on the PyPI registry."""

    #: The target pypi software component.
    component: Component

    #: The pypi registry.
    pypi_registry: PyPIRegistry

    #: The asset content.
    package_json: dict

    #: The size of the asset (in bytes). This attribute is added to match the AssetLocator
    #: protocol and is not used because pypi API registry does not provide it.
    @property
    def size_in_bytes(self) -> int:
        """Get the size of asset."""
        return -1

    @property
    def name(self) -> str:
        """Get the asset name."""
        return "package_json"

    @property
    def url(self) -> str:
        """Get the download URL of the asset.

        Note: we assume that the path parameters used to construct the URL are sanitized already.

        Returns
        -------
        str
        """
        json_endpoint = f"pypi/{self.component.name}/json"
        return urllib.parse.urljoin(self.pypi_registry.registry_url, json_endpoint)

    def download(self, dest: str) -> bool:  # pylint: disable=unused-argument
        """Download the package JSON metadata and store it in the package_json attribute.

        Returns
        -------
        bool
            ``True`` if the asset is downloaded successfully; ``False`` if not.
        """
        try:
            self.package_json = self.pypi_registry.download_package_json(self.url)
            return True
        except InvalidHTTPResponseError as error:
            logger.debug(error)
            return False

    def get_releases(self) -> dict | None:
        """Get all releases.

        Returns
        -------
        dict | None
            Version to metadata.
        """
        return json_extract(self.package_json, ["releases"], dict)

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
        return json_extract(self.package_json, ["info", "project_urls"], dict)

    def get_latest_version(self) -> str | None:
        """Get the latest version of the package.

        Returns
        -------
        str | None
            The latest version.
        """
        return json_extract(self.package_json, ["info", "version"], str)

    def get_sourcecode_url(self) -> str | None:
        """Get the url of the source distribution.

        Returns
        -------
        str | None
            The URL of the source distribution.
        """
        urls: list | None = None
        if self.component.version:
            urls = json_extract(self.package_json, ["releases", self.component.version], list)
        else:
            # Get the latest version.
            urls = json_extract(self.package_json, ["urls"], list)
        if not urls:
            return None
        for distribution in urls:
            if distribution.get("packagetype") != "sdist":
                continue
            # We intentionally check if the url is None and use empty string if that's the case.
            source_url: str = distribution.get("url") or ""
            if source_url:
                try:
                    parsed_url = urllib.parse.urlparse(source_url)
                except ValueError:
                    logger.debug("Error occurred while processing the source URL %s.", source_url)
                    return None
                if self.pypi_registry.fileserver_url_netloc and self.pypi_registry.fileserver_url_scheme:
                    configured_source_url = urllib.parse.ParseResult(
                        scheme=self.pypi_registry.fileserver_url_scheme,
                        netloc=self.pypi_registry.fileserver_url_netloc,
                        path=parsed_url.path,
                        params="",
                        query="",
                        fragment="",
                    ).geturl()
                    logger.debug("Found source URL: %s", configured_source_url)
                    return configured_source_url
        return None

    def get_latest_release_upload_time(self) -> str | None:
        """Get upload time of the latest release.

        Returns
        -------
        str | None
            The upload time of the latest release.
        """
        urls: list | None = json_extract(self.package_json, ["urls"], list)
        if urls is not None and urls:
            upload_time: str | None = urls[0].get("upload_time")
            return upload_time
        return None

    def get_sourcecode(self) -> dict[str, str] | None:
        """Get source code of the package.

        Returns
        -------
        dict[str, str] | None
            The source code of each script in the package
        """
        url: str | None = self.get_sourcecode_url()
        if url:
            source_code: dict[str, str] | None = self.pypi_registry.fetch_sourcecode(url)
            return source_code
        return None
