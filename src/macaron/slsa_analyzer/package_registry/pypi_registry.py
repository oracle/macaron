# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The module provides abstractions for the pypi package registry."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import tarfile
import tempfile
import urllib.parse
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import requests
from bs4 import BeautifulSoup, Tag
from requests import RequestException

from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError, InvalidHTTPResponseError, SourceCodeError
from macaron.json_tools import json_extract
from macaron.malware_analyzer.datetime_parser import parse_datetime
from macaron.slsa_analyzer.package_registry.package_registry import PackageRegistry
from macaron.util import send_get_http_raw

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

        # temporary directory to unzip and read all source files
        temp_dir = tempfile.mkdtemp(prefix=f"{package_name}_")
        response = send_get_http_raw(url, stream=True)
        if response is None:
            error_msg = f"Unable to find package source code using URL: {url}"
            logger.debug(error_msg)
            try:
                shutil.rmtree(temp_dir, onerror=_handle_temp_dir_clean)
            except SourceCodeError as tempdir_exception:
                tempdir_exception_msg = (
                    f"Unable to cleanup temporary directory {temp_dir} for source code: {tempdir_exception}"
                )
                logger.debug(tempdir_exception_msg)
                raise InvalidHTTPResponseError(error_msg) from tempdir_exception

            raise InvalidHTTPResponseError(error_msg)

        with tempfile.NamedTemporaryFile("+wb", delete=True) as source_file:
            try:
                for chunk in response.iter_content():
                    source_file.write(chunk)
                    source_file.flush()
            except RequestException as stream_error:
                error_msg = f"Error while streaming source file: {stream_error}"
                logger.debug(error_msg)
                try:
                    shutil.rmtree(temp_dir, onerror=_handle_temp_dir_clean)
                except SourceCodeError as tempdir_exception:
                    tempdir_exception_msg = (
                        f"Unable to cleanup temporary directory {temp_dir} for source code: {tempdir_exception}"
                    )
                    logger.debug(tempdir_exception_msg)

                raise InvalidHTTPResponseError(error_msg) from RequestException

            if tarfile.is_tarfile(source_file.name):
                try:
                    with tarfile.open(source_file.name, "r:gz") as sourcecode_tar:
                        sourcecode_tar.extractall(temp_dir, filter="data")

                except tarfile.ReadError as read_error:
                    error_msg = f"Error reading source code tar file: {read_error}"
                    logger.debug(error_msg)
                    try:
                        shutil.rmtree(temp_dir, onerror=_handle_temp_dir_clean)
                    except SourceCodeError as tempdir_exception:
                        tempdir_exception_msg = (
                            f"Unable to cleanup temporary directory {temp_dir} for source code: {tempdir_exception}"
                        )
                        logger.debug(tempdir_exception_msg)

                    raise InvalidHTTPResponseError(error_msg) from read_error

                extracted_dir = os.listdir(temp_dir)
                if len(extracted_dir) == 1 and package_name == extracted_dir[0]:
                    # structure used package name and version as top-level directory
                    temp_dir = os.path.join(temp_dir, extracted_dir[0])

            else:
                error_msg = f"Unable to extract source code from file {file_name}"
                logger.debug(error_msg)
                try:
                    shutil.rmtree(temp_dir, onerror=_handle_temp_dir_clean)
                except SourceCodeError as tempdir_exception:
                    tempdir_exception_msg = (
                        f"Unable to cleanup temporary directory {temp_dir} for source code: {tempdir_exception}"
                    )
                    logger.debug(tempdir_exception_msg)
                    raise InvalidHTTPResponseError(error_msg) from tempdir_exception

                raise InvalidHTTPResponseError(error_msg)

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
        try:
            response = requests.get(artifact_url, stream=True, timeout=40)
            response.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            logger.debug("HTTP error occurred when trying to download artifact: %s", http_err)
            return None

        if response.status_code != 200:
            logger.debug("Invalid response: %s", response.status_code)
            return None

        hash_algorithm = hashlib.sha256()
        try:
            for chunk in response.iter_content():
                hash_algorithm.update(chunk)
        except RequestException as error:
            # Something went wrong with the request, abort.
            logger.debug("Error while streaming source file: %s", error)
            response.close()
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

    #: the source code temporary location name
    package_sourcecode_path: str

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
    def sourcecode(self) -> Generator[None]:
        """Download and cleanup source code of the package with a context manager."""
        if not self.download_sourcecode():
            raise SourceCodeError("Unable to download package source code.")
        yield
        self.cleanup_sourcecode()

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

    def cleanup_sourcecode(self) -> None:
        """
        Delete the temporary directory created when downloading the source code.

        The package source code is no longer accessible after this, and the package_sourcecode_path
        attribute is set to an empty string.
        """
        if self.package_sourcecode_path:
            try:
                shutil.rmtree(self.package_sourcecode_path, onerror=_handle_temp_dir_clean)
                self.package_sourcecode_path = ""
            except SourceCodeError as tempdir_exception:
                tempdir_exception_msg = (
                    f"Unable to cleanup temporary directory {self.package_sourcecode_path}"
                    f" for source code: {tempdir_exception}"
                )
                logger.debug(tempdir_exception_msg)
                raise tempdir_exception

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

    def iter_sourcecode(self) -> Iterator[tuple[str, bytes]]:
        """
        Iterate through all source code files.

        Returns
        -------
        tuple[str, bytes]
            The source code file path, and the the raw contents of the source code file.

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

    asset = PyPIPackageJsonAsset(asset_name, asset_version, False, package_registry, {}, "")
    pypi_registry_info.metadata.append(asset)
    return asset
