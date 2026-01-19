# Copyright (c) 2023 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The module provides abstractions for the pypi package registry."""
from __future__ import annotations

import bisect
import hashlib
import logging
import os
import re
import shutil
import tarfile
import tempfile
import urllib.parse
import zipfile
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import requests
from bs4 import BeautifulSoup, Tag
from packaging.utils import InvalidWheelFilename, parse_wheel_filename

from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError, InvalidHTTPResponseError, SourceCodeError, WheelTagError
from macaron.json_tools import json_extract
from macaron.malware_analyzer.datetime_parser import parse_datetime
from macaron.slsa_analyzer.package_registry.package_registry import PackageRegistry
from macaron.util import (
    can_download_file,
    download_file_with_size_limit,
    html_is_js_challenge,
    send_get_http_raw,
    send_head_http_raw,
    stream_file_with_size_limit,
)

if TYPE_CHECKING:
    from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


def _handle_temp_dir_clean(function: Callable, path: str, onerror: tuple) -> None:
    raise SourceCodeError(f"Error removing with shutil. function={function}, " f"path={path}, excinfo={onerror}")


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
        super().__init__("PyPI Registry", "pypi")

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

    @staticmethod
    def cleanup_sourcecode_directory(
        directory: str, error_message: str | None = None, error: Exception | None = None
    ) -> None:
        """Remove the target directory, and report the passed error if present.

        Parameters
        ----------
        directory: str
            The directory to remove.
        error_message: str | None
            The error message to report.
        error: Exception | None
            The error to inherit from.

        Raises
        ------
        InvalidHTTPResponseError
            If there was an error during the operation.
        """
        if error_message:
            logger.debug(error_message)
        try:
            shutil.rmtree(directory, onerror=_handle_temp_dir_clean)
        except SourceCodeError as tempdir_exception:
            tempdir_exception_msg = (
                f"Unable to cleanup temporary directory {directory} for source code: {tempdir_exception}"
            )
            logger.debug(tempdir_exception_msg)
            raise InvalidHTTPResponseError(error_message) from tempdir_exception

        if not error_message:
            return

        if error:
            raise InvalidHTTPResponseError(error_message) from error
        raise InvalidHTTPResponseError(error_message)

    def can_download_package_sourcecode(self, url: str) -> bool:
        """Check if the package source code can be downloaded within the default file limits.

        Parameters
        ----------
        url: str
            The package source code url.

        Returns
        -------
        bool
            True if it can be downloaded within the size limits, otherwise False.
        """
        size_limit = defaults.getint("downloads", "max_download_size", fallback=10000000)
        timeout = defaults.getint("downloads", "timeout", fallback=120)
        return can_download_file(url, size_limit, timeout=timeout)

    def download_package_sourcecode(self, url: str) -> str:
        """Download the package source code from pypi registry.

        Parameters
        ----------
        url: str
            The package source code url.

        Returns
        -------
        str
            The temp directory with the source code.

        Raises
        ------
        InvalidHTTPResponseError
            If the HTTP request to the registry fails or an unexpected response is returned.
        """
        # Get name of file.
        _, _, file_name = url.rpartition("/")
        package_name = re.sub(r"\.tar\.gz$", "", file_name)

        # Temporary directory to unzip and read all source files.
        temp_dir = tempfile.mkdtemp(prefix=f"{package_name}_")
        source_file = os.path.join(temp_dir, file_name)
        timeout = defaults.getint("downloads", "timeout", fallback=120)
        size_limit = defaults.getint("downloads", "max_download_size", fallback=10000000)
        if not download_file_with_size_limit(url, {}, source_file, timeout, size_limit):
            self.cleanup_sourcecode_directory(temp_dir, "Could not download the file.")

        if not tarfile.is_tarfile(source_file):
            self.cleanup_sourcecode_directory(temp_dir, f"Unable to extract source code from file {file_name}")

        try:
            with tarfile.open(source_file, "r:gz") as sourcecode_tar:
                sourcecode_tar.extractall(temp_dir, filter="data")
        except tarfile.TarError as tar_error:
            self.cleanup_sourcecode_directory(
                temp_dir, f"Error extracting source code tar file: {tar_error}", tar_error
            )

        os.remove(source_file)

        extracted_dir = os.listdir(temp_dir)
        if len(extracted_dir) == 1 and extracted_dir[0] == package_name:
            # Structure used package name and version as top-level directory.
            temp_dir = os.path.join(temp_dir, extracted_dir[0])

        logger.debug("Temporary download and unzip of %s stored in %s", file_name, temp_dir)
        return temp_dir

    def download_package_wheel(self, url: str) -> str:
        """Download the wheel at input url.

        Parameters
        ----------
        url: str
            The wheel's url.

        Returns
        -------
        str
            The temp directory storing {distribution}-{version}.dist-info/WHEEL and
            {distribution}-{version}.dist-info/METADATA.

        Raises
        ------
        InvalidHTTPResponseError
            If the HTTP request to the registry fails or an unexpected response is returned.
        """
        # Get name of file.
        _, _, file_name = url.rpartition("/")
        # Remove the .whl to get wheel name
        wheel_name = re.sub(r"\.whl$", "", file_name)
        # Makes a directory in the OS's temp folder
        temp_dir = tempfile.mkdtemp(prefix=f"{wheel_name}_")
        # get temp_dir/file_name
        wheel_file = os.path.join(temp_dir, file_name)
        # Same timeout and size limit as in download_package_sourcecode
        timeout = defaults.getint("downloads", "timeout", fallback=120)
        size_limit = defaults.getint("downloads", "max_download_size", fallback=10000000)

        if not download_file_with_size_limit(url, {}, wheel_file, timeout, size_limit):
            self.cleanup_sourcecode_directory(temp_dir, "Could not download the file.")

        # Wheel is a zip
        if not zipfile.is_zipfile(wheel_file):
            self.cleanup_sourcecode_directory(temp_dir, f"Unable to extract source code from file {file_name}")

        try:
            # For consumer pattern
            with zipfile.ZipFile(wheel_file) as zip_file:
                members = []
                for member in zip_file.infolist():
                    if member.filename.endswith("WHEEL"):
                        members.append(member)
                    if member.filename.endswith("METADATA"):
                        members.append(member)
                # Intended suppression. The tool is unable to see that .extractall is being called with a filter
                zip_file.extractall(temp_dir, members)  # nosec B202:tarfile_unsafe_members
        except zipfile.BadZipFile as bad_zip:
            self.cleanup_sourcecode_directory(temp_dir, f"Error extracting wheel: {bad_zip}", bad_zip)

        # Now we should have it like:
        # temp_dir/wheel_name.whl
        # temp_dir/wheel_name.dist-info/

        os.remove(wheel_file)

        logger.debug("Temporary download and unzip of %s stored in %s", file_name, temp_dir)
        return temp_dir

    def get_artifact_hash(self, artifact_url: str) -> str | None:
        """Return the hash of the artifact found at the passed URL.

        Parameters
        ----------
        artifact_url
            The URL of the artifact.

        Returns
        -------
        str | None
            The hash of the artifact, or None if not found.
        """
        hash_algorithm = hashlib.sha256()
        timeout = defaults.getint("downloads", "timeout", fallback=120)
        size_limit = defaults.getint("downloads", "max_download_size", fallback=10000000)
        if not stream_file_with_size_limit(artifact_url, {}, hash_algorithm.update, timeout, size_limit):
            return None

        artifact_hash: str = hash_algorithm.hexdigest()
        logger.debug("Computed artifact hash: %s", artifact_hash)
        return artifact_hash

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
        # Important: trailing '/' avoids JS-based redirect; ensures Macaron can access the page directly
        url = urllib.parse.urljoin(self.registry_url, f"project/{package_name}/")
        response = send_get_http_raw(url)
        if response:
            html_snippets = response.content.decode("utf-8")
            if html_is_js_challenge(html_snippets):
                logger.debug("URL returned a JavaScript Challenge: %s", url)
                return None
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
        # Important: trailing '/' avoids JS-based redirect; ensures Macaron can access the page directly
        url = urllib.parse.urljoin(self.registry_url, f"user/{username}/")
        response = send_get_http_raw(url, headers=None)
        if response:
            html_snippets = response.content.decode("utf-8")
            if html_is_js_challenge(html_snippets):
                logger.debug("URL returned a JavaScript Challenge: %s", url)
                return None
            return html_snippets
        return None

    def get_packages_by_username(self, username: str) -> list[str] | None:
        """Implement custom API to get the maintainer's packages.

        Parameters
        ----------
        username: str
            The maintainer's username.

        Returns
        -------
            list[str]: A list of package names.
        """
        user_page: str | None = self.get_maintainer_profile_page(username)
        if user_page is None:
            return None

        soup = BeautifulSoup(user_page, "html.parser")
        headers = soup.find_all("h3", class_="package-snippet__title")
        packages = list({header.get_text(strip=True) for header in headers})
        return packages

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

    def get_matching_setuptools_version(self, package_release_datetime: datetime) -> str:
        """Find the setuptools that would be "latest" for the input datetime.

        Parameters
        ----------
        package_release_datetime: str
            Release datetime of a package we wish to rebuild

        Returns
        -------
            str: Matching version of setuptools
        """
        setuptools_endpoint = urllib.parse.urljoin(self.registry_url, "pypi/setuptools/json")
        setuptools_json = self.download_package_json(setuptools_endpoint)
        releases = json_extract(setuptools_json, ["releases"], dict)
        if releases:
            release_tuples = [
                (version, release_info[0].get("upload_time"))
                for version, release_info in releases.items()
                if release_info
            ]
            # Cannot assume this is sorted, as releases is just a dict
            release_tuples.sort(key=lambda x: x[1])
            # bisect_left gives position to insert package_release_datetime to maintain order, hence we do -1
            index = (
                bisect.bisect_left(
                    release_tuples, package_release_datetime, key=lambda x: datetime.strptime(x[1], "%Y-%m-%dT%H:%M:%S")
                )
                - 1
            )
            return str(release_tuples[index][0])
        # This realistically cannot happen: it would mean we somehow are trying to rebuild
        # for a package and version with no releases.
        # Return default just in case.
        return defaults.get("heuristic.pypi", "default_setuptools")

    @staticmethod
    def extract_attestation(attestation_data: dict) -> dict | None:
        """Extract the first attestation file from a PyPI attestation response.

        Parameters
        ----------
        attestation_data: dict
            The JSON data representing a bundle of attestations.

        Returns
        -------
        dict | None
            The first attestation, or None if not found.
        """
        bundle = json_extract(attestation_data, ["attestation_bundles"], list)
        if not bundle:
            logger.debug("No attestation bundle in response.")
            return None
        if len(bundle) > 1:
            logger.debug("Bundle length greater than one: %s", len(bundle))

        attestations = json_extract(bundle[0], ["attestations"], list)
        if not attestations:
            logger.debug("No attestations in response.")
            return None
        if len(attestations) > 1:
            logger.debug("More than one attestation: %s", len(attestations))

        if not isinstance(attestations[0], dict):
            logger.debug("Attestation invalid.")
            return None

        return attestations[0]


# As per https://github.com/pypi/inspector/blob/main/inspector/main.py line 125
INSPECTOR_TEMPLATE = (
    "{inspector_url_scheme}://{inspector_url_netloc}/project/"
    "{name}/{version}/packages/{first}/{second}/{rest}/{filename}"
)


@dataclass
class PyPIInspectorAsset:
    """The package PyPI inspector information."""

    #: The pypi inspector link to the tarball
    package_sdist_link: str

    #: The pypi inspector link(s) to the wheel(s)
    package_whl_links: list[str]

    #: A mapping of inspector links to whether they are reachable
    package_link_reachability: dict[str, bool]

    def __bool__(self) -> bool:
        """Determine if this inspector object is empty."""
        if (self.package_sdist_link or self.package_whl_links) and self.package_link_reachability:
            return True
        return False

    @staticmethod
    def get_structure(pypi_inspector_url: str) -> list[str] | None:
        """Get the folder structure of a package from the inspector HTML.

        Parameters
        ----------
        pypi_inspector_url: str
            The URL to a pypi inspector package page.

        Returns
        -------
        list[str] | None
            A list containing the folder structure, or None if it could not be extracted.
        """
        # TODO: may have to change this in the asset. Got a client challenge without the "/" appended.
        response = send_get_http_raw(pypi_inspector_url)
        if not response:
            return None

        html = response.content.decode("utf-8")
        soup = BeautifulSoup(html, "html.parser")
        # The package structure is present on an inspector.pypi.io page inside an unordered list (<ul>). This
        # is the only unordered list on the page.
        if soup.ul is None:
            return None

        # All the file names sit inside <li> elements in our unordered list, under <a> tags with the 'href' class.
        files_list = []
        for element in soup.ul.find_all("li"):
            if element.a and element.a["href"]:
                files_list.append(element.a["href"])

        return files_list


@dataclass
class PyPIPackageJsonAsset:
    """The package JSON hosted on the PyPI registry."""

    #: The target pypi software component name.
    component_name: str

    #: The target pypi software component version.
    component_version: str | None

    #: Whether the component of this asset has a related repository.
    has_repository: bool

    #: The pypi registry.
    pypi_registry: PyPIRegistry

    #: The asset content.
    package_json: dict

    #: The source code temporary location name.
    package_sourcecode_path: str = field(init=False)

    #: The wheel temporary location name.
    wheel_path: str = field(init=False)

    #: Name of the wheel file.
    wheel_filename: str = field(init=False)

    #: The datetime that the wheel was uploaded.
    package_upload_time: datetime | None = field(default=None, init=False)

    #: The pypi inspector information about this package
    inspector_asset: PyPIInspectorAsset

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
        json_endpoint = f"pypi/{self.component_name}/json"
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

    def get_sourcecode_url(self, package_type: str = "sdist") -> str | None:
        """Get the url of the source distribution.

        Parameters
        ----------
        package_type: str
            The package type to retrieve the URL of.

        Returns
        -------
        str | None
            The URL of the source distribution.
        """
        if self.component_version:
            urls = json_extract(self.package_json, ["releases", self.component_version], list)
        else:
            # Get the latest version.
            urls = json_extract(self.package_json, ["urls"], list)
        if not urls:
            return None
        for distribution in urls:
            if distribution.get("packagetype") != package_type:
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

    def get_wheel_url(self, tag: str = "none-any") -> str | None:
        """Get url of wheel corresponding to specified tag.

        Parameters
        ----------
        tag: str
            Wheel tag to match. Defaults to none-any.

        Returns
        -------
        str | None
            URL of the wheel.
        """
        if self.component_version:
            urls = json_extract(self.package_json, ["releases", self.component_version], list)
        else:
            # Get the latest version.
            urls = json_extract(self.package_json, ["urls"], list)
        if not urls:
            return None
        for distribution in urls:
            # In this way we have a package_upload_time even if we cannot find the wheel.
            try:
                self.package_upload_time = datetime.strptime(distribution.get("upload_time") or "", "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                logging.debug("Could not parse the uploaded datetime: %s", distribution.get("upload_time") or "")
            # Only examine wheels
            if distribution.get("packagetype") != "bdist_wheel":
                continue
            file_name: str = distribution.get("filename") or ""
            if not file_name.endswith(f"{tag}.whl"):
                continue
            self.wheel_filename = file_name
            # Continue to getting url
            wheel_url: str = distribution.get("url") or ""
            if wheel_url:
                try:
                    self.package_upload_time = datetime.strptime(
                        distribution.get("upload_time") or "", "%Y-%m-%dT%H:%M:%S"
                    )
                except ValueError:
                    logging.debug("Could not parse the uploaded datetime: %s", distribution.get("upload_time") or "")
                try:
                    parsed_url = urllib.parse.urlparse(wheel_url)
                except ValueError:
                    logger.debug("Error occurred while processing the wheel URL %s.", wheel_url)
                    return None
                if self.pypi_registry.fileserver_url_netloc and self.pypi_registry.fileserver_url_scheme:
                    configured_wheel_url = urllib.parse.ParseResult(
                        scheme=self.pypi_registry.fileserver_url_scheme,
                        netloc=self.pypi_registry.fileserver_url_netloc,
                        path=parsed_url.path,
                        params="",
                        query="",
                        fragment="",
                    ).geturl()
                    logger.debug("Found wheel URL: %s", configured_wheel_url)
                    return configured_wheel_url
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

    @contextmanager
    def wheel(self, download_binaries: bool) -> Generator[None]:
        """Download and cleanup wheel of the package with a context manager."""
        if download_binaries:
            raise WheelTagError("Macaron does not currently support analysis of non-pure Python wheels.")
        if not self.download_wheel():
            raise SourceCodeError("Unable to download requested wheel.")
        yield
        if self.wheel_path:
            # Name for cleanup_sourcecode_directory could be refactored here
            PyPIRegistry.cleanup_sourcecode_directory(self.wheel_path)

    def download_wheel(self) -> bool:
        """Download and extract wheel metadata to a temporary directory.

        Returns
        -------
        bool
            ``True`` if the wheel is downloaded and extracted successfully; ``False`` if not.
        """
        url = self.get_wheel_url()
        if url:
            try:
                self.wheel_path = self.pypi_registry.download_package_wheel(url)
                return True
            except InvalidHTTPResponseError as error:
                logger.debug(error)
        return False

    def has_pure_wheel(self) -> bool:
        """Check whether the PURL has a pure wheel from its package json.

        Returns
        -------
        bool
            Whether the PURL has a pure wheel or not.
        """
        if self.component_version:
            urls = json_extract(self.package_json, ["releases", self.component_version], list)
        else:
            # Get the latest version.
            urls = json_extract(self.package_json, ["urls"], list)
        if not urls:
            return False
        for distribution in urls:
            file_name: str = distribution.get("filename") or ""
            # Parse out and check none and any
            # Catch exceptions
            try:
                _, _, _, tags = parse_wheel_filename(file_name)
                # Check if none and any are in the tags (i.e. the wheel is pure)
                # Technically a wheel can have multiple tag sets. Our condition for
                # a pure wheel is that it has only one tag set with abi "none" and
                # platform "any"
                if len(tags) == 1 and all(tag.abi == "none" and tag.platform == "any" for tag in tags):
                    return True
            except InvalidWheelFilename:
                logger.debug("Could not parse wheel name.")
                return False
        return False

    @contextmanager
    def sourcecode(self) -> Generator[None]:
        """Download and cleanup source code of the package with a context manager."""
        if not self.download_sourcecode():
            raise SourceCodeError("Unable to download package source code.")
        yield
        if self.package_sourcecode_path:
            PyPIRegistry.cleanup_sourcecode_directory(self.package_sourcecode_path)

    def download_sourcecode(self) -> bool:
        """Get the source code of the package and store it in a temporary directory.

        Returns
        -------
        bool
            ``True`` if the source code is downloaded successfully; ``False`` if not.
        """
        url = self.get_sourcecode_url()
        if url:
            try:
                self.package_sourcecode_path = self.pypi_registry.download_package_sourcecode(url)
                return True
            except InvalidHTTPResponseError as error:
                logger.debug(error)
        return False

    def can_download_sourcecode(self) -> bool:
        """Return whether the package source code can be downloaded within the download file size limits.

        Returns
        -------
        bool
            ``True`` if the source code can be downloaded; ``False`` if not.
        """
        url = self.get_sourcecode_url()
        if url:
            return self.pypi_registry.can_download_package_sourcecode(url)
        return False

    def get_sourcecode_file_contents(self, path: str) -> bytes:
        """
        Get the contents of a single source code file specified by the path.

        The path can be relative to the package_sourcecode_path attribute, or an absolute path.

        Parameters
        ----------
        path: str
            The absolute or relative to package_sourcecode_path file path to open.

        Returns
        -------
        bytes
            The raw contents of the source code file.

        Raises
        ------
        SourceCodeError
            if the source code has not been downloaded, or there is an error accessing the file.
        """
        if not self.package_sourcecode_path:
            error_msg = "No source code files have been downloaded"
            logger.debug(error_msg)
            raise SourceCodeError(error_msg)

        if not os.path.isabs(path):
            path = os.path.join(self.package_sourcecode_path, path)

        if not os.path.exists(path):
            error_msg = f"Unable to locate file {path}"
            logger.debug(error_msg)
            raise SourceCodeError(error_msg)

        try:
            with open(path, "rb") as file:
                return file.read()
        except OSError as read_error:
            error_msg = f"Unable to read file {path}: {read_error}"
            logger.debug(error_msg)
            raise SourceCodeError(error_msg) from read_error

    def file_exists(self, path: str) -> bool:
        """Check if a file exists in the downloaded source code.

        The path can be relative to the package_sourcecode_path attribute, or an absolute path.

        Parameters
        ----------
        path: str
            The absolute or relative to package_sourcecode_path file path to check for.

        Returns
        -------
            bool: Whether or not a file at path absolute or relative to package_sourcecode_path exists.
        """
        if not self.package_sourcecode_path:
            # No source code files were downloaded
            return False

        if not os.path.isabs(path):
            path = os.path.join(self.package_sourcecode_path, path)

        if not os.path.exists(path):
            # Could not find a file at that path
            return False

        return True

    def iter_sourcecode(self) -> Iterator[tuple[str, bytes]]:
        """
        Iterate through all source code files.

        Returns
        -------
        tuple[str, bytes]
            The source code file path, and the raw contents of the source code file.

        Raises
        ------
        SourceCodeError
            if the source code has not been downloaded.
        """
        if not self.package_sourcecode_path:
            error_msg = "No source code files have been downloaded"
            logger.debug(error_msg)
            raise SourceCodeError(error_msg)

        for root, _directories, files in os.walk(self.package_sourcecode_path):
            for file in files:
                if root == ".":
                    root_path = os.getcwd() + os.linesep
                else:
                    root_path = root
                filepath = os.path.join(root_path, file)

                with open(filepath, "rb") as handle:
                    contents = handle.read()

                yield filepath, contents

    def get_sha256(self) -> str | None:
        """Get the sha256 hash of the artifact from its payload.

        Returns
        -------
        str | None
            The sha256 hash of the artifact, or None if not found.
        """
        if not self.package_json and not self.download(""):
            return None

        if not self.component_version:
            artifact_hash = json_extract(self.package_json, ["urls", 0, "digests", "sha256"], str)
        else:
            artifact_hash = json_extract(
                self.package_json, ["releases", self.component_version, 0, "digests", "sha256"], str
            )
        logger.debug("Found sha256 hash: %s", artifact_hash)
        return artifact_hash

    def get_inspector_src_preview_links(self) -> bool:
        """Generate PyPI inspector links for this package version's distributions and fill in the inspector asset.

        Returns
        -------
        bool
            True if the link generation was successful, False otherwise.
        """
        if self.inspector_asset:
            return True

        if not self.package_json and not self.download(""):
            logger.debug("No package metadata available, cannot get links")
            return False

        releases = self.get_releases()
        if releases is None:
            logger.debug("Package has no releases, cannot create inspector links.")
            return False

        version = self.component_version
        if self.component_version is None:
            version = self.get_latest_version()

        if version is None:
            logger.debug("No version set, and no latest version exists. cannot create inspector links.")
            return False

        distributions = json_extract(releases, [version], list)

        if not distributions:
            logger.debug("Package has no distributions for release version %s. Cannot create inspector links.", version)
            return False

        for distribution in distributions:
            package_type = json_extract(distribution, ["packagetype"], str)
            if package_type is None:
                logger.debug("The version %s has no 'package type' field in a distribution", version)
                continue

            name = json_extract(self.package_json, ["info", "name"], str)
            if name is None:
                logger.debug("The version %s has no 'name' field in a distribution", version)
                continue

            blake2b_256 = json_extract(distribution, ["digests", "blake2b_256"], str)
            if blake2b_256 is None:
                logger.debug("The version %s has no 'blake2b_256' field in a distribution", version)
                continue

            filename = json_extract(distribution, ["filename"], str)
            if filename is None:
                logger.debug("The version %s has no 'filename' field in a distribution", version)
                continue

            link = INSPECTOR_TEMPLATE.format(
                inspector_url_scheme=self.pypi_registry.inspector_url_scheme,
                inspector_url_netloc=self.pypi_registry.inspector_url_netloc,
                name=name,
                version=version,
                first=blake2b_256[0:2],
                second=blake2b_256[2:4],
                rest=blake2b_256[4:],
                filename=filename,
            )

            # Use a head request because we don't care about the response contents.
            reachable = False
            if send_head_http_raw(link):
                reachable = True  # Link was reachable.

            if package_type == "sdist":
                self.inspector_asset.package_sdist_link = link
                self.inspector_asset.package_link_reachability[link] = reachable
            elif package_type == "bdist_wheel":
                self.inspector_asset.package_whl_links.append(link)
                self.inspector_asset.package_link_reachability[link] = reachable
            else:  # No other package types exist, so else statement should never occur.
                logger.debug("Unknown package distribution type: %s", package_type)

        # If all distributions were invalid and went along a 'continue' path.
        return bool(self.inspector_asset)

    def get_chronologically_suitable_setuptools_version(self) -> str:
        """Find version of setuptools that would be "latest" for this package.

        Returns
        -------
        str
            Chronologically likeliest setuptools version
        """
        if self.package_upload_time:
            return self.pypi_registry.get_matching_setuptools_version(self.package_upload_time)
        # If we cannot infer upload time for the package, return the default
        return defaults.get("heuristic.pypi", "default_setuptools")


def find_or_create_pypi_asset(
    asset_name: str, asset_version: str | None, pypi_registry_info: PackageRegistryInfo
) -> PyPIPackageJsonAsset | None:
    """Find the matching asset in the provided package registry information, or if not found, create and add it.

    Parameters
    ----------
    asset_name: str
        The name of the asset.
    asset_version: str | None
        The version of the asset.
    pypi_registry_info:
        The package registry information. If a new asset is created, it will be added to the metadata of this registry.

    Returns
    -------
    PyPIPackageJsonAsset | None
        The asset, or None if not found.
    """
    asset = next(
        (
            asset
            for asset in pypi_registry_info.metadata
            if isinstance(asset, PyPIPackageJsonAsset) and asset.component_name == asset_name
        ),
        None,
    )

    if asset:
        return asset

    package_registry = pypi_registry_info.package_registry
    if not isinstance(package_registry, PyPIRegistry):
        logger.debug("Failed to create PyPIPackageJson asset.")
        return None

    asset = PyPIPackageJsonAsset(asset_name, asset_version, False, package_registry, {}, PyPIInspectorAsset("", [], {}))
    pypi_registry_info.metadata.append(asset)
    return asset
