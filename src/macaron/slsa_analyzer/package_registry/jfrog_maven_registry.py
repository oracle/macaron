# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Assets on a package registry."""

from __future__ import annotations

import json
import logging
from typing import NamedTuple
from urllib.parse import SplitResult, urlunsplit

import requests

from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.package_registry.package_registry import PackageRegistry
from macaron.util import JsonType

logger: logging.Logger = logging.getLogger(__name__)


class JFrogMavenAsset(NamedTuple):
    """An asset hosted on a JFrog Artifactory repository with Maven layout."""

    #: The name of the Maven asset.
    name: str
    #: The group id.
    group_id: str
    #: The artifact id.
    artifact_id: str
    #: The version of the Maven asset.
    version: str
    #: The metadata of the JFrog Maven asset.
    metadata: JFrogMavenAssetMetadata
    #: The JFrog repo that acts as a package registry following the
    #: `Maven layout <https://maven.apache.org/repository/layout.html>`_.
    jfrog_maven_registry: JFrogMavenRegistry

    @property
    def url(self) -> str:
        """Get the URL to the asset.

        This URL can be used to download the asset.
        """
        return self.metadata.download_uri

    @property
    def sha256_digest(self) -> str:
        """Get the SHA256 digest of the asset."""
        return self.metadata.sha256_digest

    @property
    def size_in_bytes(self) -> int:
        """Get the size of the asset (in bytes)."""
        return self.metadata.size_in_bytes

    def download(self, dest: str) -> bool:
        """Download the asset.

        Parameters
        ----------
        dest : str
            The local destination where the asset is downloaded to.
            Note that this must include the file name.

        Returns
        -------
        bool
            ``True`` if the asset is downloaded successfully; ``False`` if not.
        """
        return self.jfrog_maven_registry.download_asset(self.url, dest)


class JFrogMavenAssetMetadata(NamedTuple):
    """Metadata of an asset on a JFrog Maven registry."""

    #: The size of the asset (in bytes).
    size_in_bytes: int
    #: The SHA256 digest of the asset.
    sha256_digest: str
    #: The download URI of the asset.
    download_uri: str


class JFrogMavenRegistry(PackageRegistry):
    """A JFrog Artifactory repository that acts as a package registry with Maven layout.

    For more details on JFrog Artifactory repository, see:
    https://jfrog.com/help/r/jfrog-artifactory-documentation/repository-management
    """

    def __init__(
        self,
        hostname: str | None = None,
        repo: str | None = None,
        request_timeout: int | None = None,
        download_timeout: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        """
        Instantiate a JFrogMavenRegistry object.

        Parameters
        ----------
        hostname : str
            The hostname of the JFrog instance.
        repo : str | None
            The Artifactory repository with Maven layout on the JFrog instance.
        request_timeout : int | None
            The timeout (in seconds) for regular requests made to the package registry.
        download_timeout : int | None
            The timeout (in seconds) for downloading files from the package registry.
        enabled : bool | None
            Whether the package registry should be active in the analysis or not.
            "Not active" means no target repo/software component can be matched against
            this package registry.
        """
        self.hostname = hostname or ""
        self.repo = repo or ""
        self.request_timeout = request_timeout or 10
        self.download_timeout = download_timeout or 120
        self.enabled = enabled or False
        super().__init__("JFrog Maven Registry")

    def load_defaults(self) -> None:
        """Load the .ini configuration for the current package registry.

        Raises
        ------
        ConfigurationError
            If there is a schema violation in the ``package_registry.jfrog.maven`` section.
        """
        section_name = "package_registry.jfrog.maven"
        if not defaults.has_section(section_name):
            return
        section = defaults[section_name]

        self.hostname = section.get("hostname")
        if not self.hostname:
            raise ConfigurationError(
                f'The "hostname" key is missing in section [{section_name}] of the .ini configuration file.'
            )

        self.repo = section.get("repo")
        if not self.repo:
            raise ConfigurationError(
                f'The "repo" key is missing in section [{section_name}] of the .ini configuration file.'
            )

        try:
            self.request_timeout = defaults.getint("requests", "timeout", fallback=10)
        except ValueError as error:
            raise ConfigurationError(
                f'The value of "timeout" in section [requests] ' f"of the .ini configuration file is invalid: {error}",
            ) from error

        try:
            self.download_timeout = section.getint(
                "download_timeout",
                fallback=self.request_timeout,
            )
        except ValueError as error:
            raise ConfigurationError(
                f'The value of "download_timeout" in section [{section_name}] '
                f"of the .ini configuration file is invalid: {error}",
            ) from error

        self.enabled = True

    def is_detected(self, build_tool: BaseBuildTool) -> bool:
        """Detect if artifacts of the repo under analysis can possibly be published to this package registry.

        The detection here is based on the repo's detected build tool.
        If the package registry is compatible with the given build tool, it can be a
        possible place where the artifacts produced from the repo are published.

        ``JFrogMavenRegistry`` is compatible with Maven and Gradle.

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
        if not self.enabled:
            return False
        compatible_build_tool_classes = [Maven, Gradle]
        for build_tool_class in compatible_build_tool_classes:
            if isinstance(build_tool, build_tool_class):
                return True
        return False

    def construct_maven_repository_path(
        self,
        group_id: str,
        artifact_id: str | None = None,
        version: str | None = None,
        asset_name: str | None = None,
    ) -> str:
        """Construct a path to a folder or file on the registry, assuming Maven repository layout.

        For more details regarding Maven repository layout, see the following:
        - https://maven.apache.org/repository/layout.html
        - https://maven.apache.org/guides/mini/guide-naming-conventions.html

        Parameters
        ----------
        group_id : str
            The group id of a Maven package.
        artifact_id : str
            The artifact id of a Maven package.
        version : str
            The version of a Maven package.
        asset_name : str
            The asset name.

        Returns
        -------
        str
            The path to a folder or file on the registry.
        """
        path = group_id.replace(".", "/")
        if artifact_id:
            path = "/".join([path, artifact_id])
        if version:
            path = "/".join([path, version])
        if asset_name:
            path = "/".join([path, asset_name])
        return path

    def fetch_artifact_ids(self, group_id: str) -> list[str]:
        """Get all artifact ids under a group id.

        This is done by fetching all children folders under the group folder on the registry.

        Parameters
        ----------
        group_id : str
            The group id.

        Returns
        -------
        list[str]
            The artifacts ids under the group.
        """
        folder_info_url = self.construct_folder_info_url(
            folder_path=self.construct_maven_repository_path(group_id),
        )

        try:
            response = requests.get(url=folder_info_url, timeout=self.request_timeout)
        except requests.exceptions.RequestException as error:
            logger.debug("Failed to retrieve artifact ids for group %s: %s", group_id, error)
            return []

        if response.status_code == 200:
            folder_info_payload = response.text
        else:
            logger.debug(
                "Error retrieving artifact ids of group %s: got response with status code %d.",
                group_id,
                response.status_code,
            )
            return []

        artifact_ids = self.extract_folder_names_from_folder_info_payload(folder_info_payload)
        return artifact_ids

    def construct_folder_info_url(self, folder_path: str) -> str:
        """Construct a URL for the JFrog Folder Info API.

        Documentation: https://jfrog.com/help/r/jfrog-rest-apis/folder-info.

        Parameters
        ----------
        folder_path : str
            The path to the folder.

        Returns
        -------
        str
            The URL to request the info of the folder.
        """
        url = urlunsplit(
            SplitResult(
                scheme="https",
                netloc=self.hostname,
                path=f"/api/storage/{self.repo}/{folder_path}",
                query="",
                fragment="",
            )
        )
        return url

    def construct_file_info_url(self, file_path: str) -> str:
        """Construct a URL for the JFrog File Info API.

        Documentation: https://jfrog.com/help/r/jfrog-rest-apis/file-info.

        Parameters
        ----------
        file_path : str
            The path to the file.

        Returns
        -------
        str
            The URL to request the info of the file.
        """
        return urlunsplit(
            SplitResult(
                scheme="https",
                netloc=self.hostname,
                path=f"/api/storage/{self.repo}/{file_path}",
                query="",
                fragment="",
            )
        )

    def construct_latest_version_url(
        self,
        group_id: str,
        artifact_id: str,
    ) -> str:
        """Construct a URL for the JFrog Latest Version Search API.

        The response payload includes the latest version of the package with the given
        group id and artifact id.
        Documentation: https://jfrog.com/help/r/jfrog-rest-apis/artifact-latest-version-search-based-on-layout.

        Parameters
        ----------
        group_id : str
            The group id of the package.
        artifact_id: str
            The artifact id of the package.

        Returns
        -------
        str
            The URL to request the latest version of the package.
        """
        return urlunsplit(
            SplitResult(
                scheme="https",
                netloc=self.hostname,
                path="/api/search/latestVersion",
                query="&".join(
                    [
                        f"repos={self.repo}",
                        f"g={group_id}",
                        f"a={artifact_id}",
                    ]
                ),
                fragment="",
            )
        )

    def fetch_latest_version(self, group_id: str, artifact_id: str) -> str | None:
        """Fetch the latest version of a Java package on this JFrog Maven registry.

        Parameters
        ----------
        group_id : str
            The group id of the Java package.
        artifact_id : str
            The artifact id of the Java package.

        Returns
        -------
        str | None
            The latest version of the Java package if it could be retrieved, or ``None`` otherwise.
        """
        logger.debug(
            "Retrieving latest version of Java package %s:%s.",
            group_id,
            artifact_id,
        )

        url = self.construct_latest_version_url(
            group_id=group_id,
            artifact_id=artifact_id,
        )

        try:
            response = requests.get(url, timeout=self.request_timeout)
        except requests.exceptions.RequestException as error:
            logger.debug(
                "Failed to retrieve the latest version of Java package %s:%s: %s",
                group_id,
                artifact_id,
                error,
            )
            return None

        if response.status_code == 200:
            version = response.text
            return version

        logger.debug(
            "Failed to retrieve the latest version of Java package %s:%s. Got response with status code %d: %s",
            group_id,
            artifact_id,
            response.status_code,
            response.text,
        )
        return None

    def fetch_asset_names(
        self,
        group_id: str,
        artifact_id: str,
        version: str,
        extensions: set[str] | None = None,
    ) -> list[str]:
        """Retrieve the metadata of assets published for a version of a Maven package.

        Parameters
        ----------
        group_id : str
            The group id of the Maven package.
        artifact_id : str
            The artifact id of the Maven package.
        version : str
            The version of the Maven package.
        extensions : set[str] | None
            The set of asset extensions.
            Only assets with names ending in these extensions are fetched.
            If this is ``None``, then all assets are returned regardless of their extensions.

        Returns
        -------
        list[str]
            The list of asset names.
        """
        folder_path = self.construct_maven_repository_path(
            group_id=group_id,
            artifact_id=artifact_id,
            version=version,
        )
        url = self.construct_folder_info_url(folder_path=folder_path)

        try:
            response = requests.get(url=url, timeout=self.request_timeout)
        except requests.exceptions.RequestException as error:
            logger.debug(
                "Failed to fetch assets of Java package %s:%s: %s",
                group_id,
                artifact_id,
                error,
            )
            return []

        if response.status_code != 200:
            logger.debug(
                "Failed to fetch the assets of Java package %s:%s: got response with status code %d.",
                group_id,
                artifact_id,
                response.status_code,
            )
            return []

        return self.extract_file_names_from_folder_info_payload(
            folder_info_payload=response.text,
            extensions=extensions,
        )

    def _extract_children_form_folder_info_payload(self, folder_info_payload: str) -> list[JsonType]:
        """Extract the ``children`` field from the JFrog Folder Info payload.

        Note: Currently, we do not try to validate the schema of the payload. Rather, we only
        try to read things that we can recognise.

        Parameters
        ----------
        folder_info_payload : JsonType
            The JSON payload of a Folder Info request.
            Documentation: https://jfrog.com/help/r/jfrog-rest-apis/folder-info.

        Returns
        -------
        list[JsonType]
            The result of extracting the ``children`` field from the Folder Info payload.
        """
        try:
            json_payload: JsonType = json.loads(folder_info_payload)
        except json.JSONDecodeError as error:
            logger.debug("Failed to decode the Folder Info payload: %s.", error)
            return []

        if not isinstance(json_payload, dict):
            logger.debug("Got unexpected value type for the Folder Info payload. Expected a JSON object.")
            return []

        children = json_payload.get("children", [])
        if not isinstance(children, list):
            logger.debug("Got unexpected value for the 'children' field in the Folder Info payload. Expected a list.")
            return []

        return children

    def extract_folder_names_from_folder_info_payload(
        self,
        folder_info_payload: str,
    ) -> list[str]:
        """Extract a list of folder names from the Folder Info payload of a Maven group folder.

        Parameters
        ----------
        folder_info_payload : str
            The Folder Info payload.

        Returns
        -------
        list[str]
            The artifact ids found in the payload.
        """
        children = self._extract_children_form_folder_info_payload(folder_info_payload)

        folder_names = []

        for child in children:
            if not isinstance(child, dict):
                continue

            is_folder = child.get("folder", True)
            if not isinstance(is_folder, bool) or not is_folder:
                continue

            uri = child.get("uri", "")
            if not isinstance(uri, str) or not uri:
                continue
            folder_name = uri.lstrip("/")
            folder_names.append(folder_name)

        return folder_names

    def extract_file_names_from_folder_info_payload(
        self,
        folder_info_payload: str,
        extensions: set[str] | None = None,
    ) -> list[str]:
        """Extract file names from the Folder Info response payload.

        For the schema of this payload and other details regarding the API, see:
        https://jfrog.com/help/r/jfrog-rest-apis/folder-info.

        Note: Currently, we do not try to validate the schema of the payload. Rather, we only
        try to read as much as possible things that we can recognise.

        Parameters
        ----------
        folder_info_payload : JsonType
            The JSON payload of a Folder Info response.
        extensions : set[str] | None
            The set of allowed extensions.
            Filenames not ending in these extensions are omitted from the result.
            If this is ``None``, then all file names are returned regardless of their extensions.

        Returns
        -------
        list[str]
            The list of filenames in the folder, extracted from the payload.
        """
        children = self._extract_children_form_folder_info_payload(folder_info_payload)

        asset_names = []

        for child in children:
            if not isinstance(child, dict):
                continue

            is_folder = child.get("folder", True)
            if not isinstance(is_folder, bool) or is_folder:
                continue

            uri = child.get("uri", "")
            if not isinstance(uri, str) or not uri:
                continue
            asset_name = uri.lstrip("/")
            if not extensions or any(asset_name.endswith(extension) for extension in extensions):
                asset_names.append(asset_name)

        return asset_names

    def fetch_asset_metadata(
        self,
        group_id: str,
        artifact_id: str,
        version: str,
        asset_name: str,
    ) -> JFrogMavenAssetMetadata | None:
        """Fetch an asset's metadata from JFrog.

        Parameters
        ----------
        group_id : str
            The group id of the package containing the asset.
        artifact_id : str
            The artifact id of the package containing the asset.
        version : str
            The version of the package containing the asset.
        asset_name : str
            The name of the asset.

        Returns
        -------
        JFrogMavenAssetMetadata | None
            The asset's metadata, or ``None`` if the metadata cannot be retrieved.
        """
        file_path = self.construct_maven_repository_path(
            group_id=group_id,
            artifact_id=artifact_id,
            version=version,
            asset_name=asset_name,
        )
        url = self.construct_file_info_url(file_path)

        try:
            response = requests.get(url=url, timeout=self.request_timeout)
        except requests.exceptions.RequestException as error:
            logger.debug(
                "Failed to fetch metadata of package %s:%s:%s: %s",
                group_id,
                artifact_id,
                version,
                error,
            )
            return None

        if response.status_code == 200:
            file_info_payload = response.text
        else:
            logger.debug(
                "Failed to fetch metadata of package %s:%s:%s. Got response with status code %d: %s",
                group_id,
                artifact_id,
                version,
                response.status_code,
                response.text,
            )
            return None

        try:
            return self.extract_asset_metadata_from_file_info_payload(file_info_payload)
        except KeyError as error:
            logger.debug("Failed to fetch metadata of package %s:%s:%s: %s", group_id, artifact_id, version, error)
            return None

    def extract_asset_metadata_from_file_info_payload(
        self,
        file_info_payload: str,
    ) -> JFrogMavenAssetMetadata | None:
        """Extract the metadata of an asset from the File Info request payload.

        Documentation: https://jfrog.com/help/r/jfrog-rest-apis/file-info.

        Parameters
        ----------
        file_info_payload : str
            The File Info request payload used to extract the metadata of an asset.

        Returns
        -------
        JFrogMavenAssetMetadata | None
            The asset's metadata, or ``None`` if the metadata cannot be retrieved.
        """
        try:
            json_payload: JsonType = json.loads(file_info_payload)
        except json.JSONDecodeError as error:
            logger.debug("Failed to decode the File Info payload: %s.", error)
            return None

        if not isinstance(json_payload, dict):
            logger.debug("Got unexpected value for File Info payload. Expected a JSON object.")
            return None

        checksums = json_payload.get("checksums", {})

        if not isinstance(checksums, dict):
            logger.debug(
                "Got unexpected value for the 'checksums' field in the File Info payload. Expected a JSON object."
            )
            return None

        sha256_checksum = checksums.get("sha256")
        if not sha256_checksum or not isinstance(sha256_checksum, str):
            logger.debug("Could not extract the SHA256 checksum from the File Info payload.")
            return None

        size_in_bytes_input = json_payload.get("size")
        if not size_in_bytes_input or not isinstance(size_in_bytes_input, str):
            logger.debug("Could not extract the value of the 'size' field from the File Info payload.")
            return None

        try:
            size_in_bytes = int(size_in_bytes_input)
        except ValueError:
            logger.debug("Invalid value for the 'size' field in the File Info payload.")
            return None

        download_uri = json_payload.get("downloadUri")
        if not download_uri or not isinstance(download_uri, str):
            logger.debug("Could not extract the value of the 'download_uri' field from the File Info payload.")
            return None

        return JFrogMavenAssetMetadata(
            size_in_bytes=size_in_bytes,
            sha256_digest=sha256_checksum,
            download_uri=download_uri,
        )

    def fetch_assets(
        self,
        group_id: str,
        artifact_id: str,
        version: str,
        extensions: set[str] | None = None,
    ) -> list[JFrogMavenAsset]:
        """Fetch the assets of a Maven package.

        Parameters
        ----------
        group_id : str
            The group id of the Maven package.
        artifact_id : str
            The artifact id of the Maven package.
        version : str
            The version of the Maven package.
        extensions : set[str] | None
            The extensions of the assets to fetch.
            If this is ``None``, all available assets are fetched.

        Returns
        -------
        list[JFrogMavenAsset]
            The list of assets of the package.
        """
        asset_names = self.fetch_asset_names(
            group_id=group_id,
            artifact_id=artifact_id,
            version=version,
            extensions=extensions,
        )

        assets = []

        for asset_name in asset_names:
            asset_metadata = self.fetch_asset_metadata(
                group_id=group_id,
                artifact_id=artifact_id,
                version=version,
                asset_name=asset_name,
            )
            if asset_metadata:
                assets.append(
                    JFrogMavenAsset(
                        name=asset_name,
                        group_id=group_id,
                        artifact_id=artifact_id,
                        version=version,
                        metadata=asset_metadata,
                        jfrog_maven_registry=self,
                    )
                )

        return assets

    def construct_asset_url(
        self,
        group_id: str,
        artifact_id: str,
        version: str,
        asset_name: str,
    ) -> str:
        """Get the URL to download an asset.

        Parameters
        ----------
        group_id : str
            The group id of the package containing the asset.
        artifact_id : str
            The artifact id of the package containing the asset.
        version : str
            The version of the package containing the asset.
        asset_name : str
            The name of the asset.

        Returns
        -------
        str
            The URL to the asset, which can be use for downloading the asset.
        """
        group_path = self.construct_maven_repository_path(group_id)
        return urlunsplit(
            SplitResult(
                scheme="https",
                netloc=self.hostname,
                path=f"{self.repo}/{group_path}/{artifact_id}/{version}/{asset_name}",
                query="",
                fragment="",
            )
        )

    def download_asset(self, url: str, dest: str) -> bool:
        """Download an asset from the given URL to a given location.

        Parameters
        ----------
        url : str
            The URL to the asset on the package registry.
        dest : str
            The local destination where the asset is downloaded to.

        Returns
        -------
        bool
            ``True`` if the file is downloaded successfully; ``False`` if not.
        """
        try:
            response = requests.get(url=url, timeout=self.download_timeout)
        except requests.exceptions.RequestException as error:
            logger.debug("Failed to download asset from %s. Error: %s", url, error)
            return False

        if response.status_code != 200:
            logger.debug(
                "Failed to download asset from %s. Got response with status code %d: %s",
                url,
                response.status_code,
                response.text,
            )
            return False

        try:
            with open(dest, "wb") as file:
                file.write(response.content)
        except OSError as error:
            logger.debug(
                "Failed to write the downloaded asset from %s to %s. Error: %s",
                url,
                dest,
                error,
            )
            return False

        return True
