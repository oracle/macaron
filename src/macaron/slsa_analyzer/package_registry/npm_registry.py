# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The module provides abstractions for the npm package registry."""

import json
import logging
from typing import NamedTuple
from urllib.parse import SplitResult, urlunsplit

import requests

from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError, InvalidHTTPResponseError
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.build_tool.npm import NPM
from macaron.slsa_analyzer.build_tool.yarn import Yarn
from macaron.slsa_analyzer.package_registry.package_registry import PackageRegistry
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class NPMRegistry(PackageRegistry):
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
        super().__init__("npm Registry")

    def load_defaults(self) -> None:
        """Load the .ini configuration for the current package registry.

        Raises
        ------
        ConfigurationError
            If there is a schema violation in the ``npm registry`` section.
        """
        section_name = "package_registry.npm"
        if not defaults.has_section(section_name):
            self.enabled = False
            return
        section = defaults[section_name]

        if not section.getboolean("enabled", fallback=True):
            self.enabled = False
            logger.debug("npm registry is disabled in section [%s] of the .ini configuration file.", section_name)
            return

        self.hostname = section.get("hostname")
        if not self.hostname:
            raise ConfigurationError(
                f'The "hostname" key is missing in section [{section_name}] of the .ini configuration file.'
            )

        self.attestation_endpoint = section.get("attestation_endpoint")

        if not self.attestation_endpoint:
            raise ConfigurationError(
                f'The "attestation_endpoint" key is missing in section [{section_name}] of the .ini configuration file.'
            )

        try:
            self.request_timeout = section.getint("request_timeout", fallback=10)
        except ValueError as error:
            raise ConfigurationError(
                f'The "request_timeout" value in section [{section_name}]'
                f"of the .ini configuration file is invalid: {error}",
            ) from error

    def is_detected(self, build_tool: BaseBuildTool) -> bool:
        """Detect if artifacts under analysis can be published to this package registry.

        The detection here is based on the repo's detected build tools.
        If the package registry is compatible with the given build tools, it can be a
        possible place where the artifacts are published.

        ``NPMRegistry`` is compatible with npm and Yarn build tools.

        Note: if the npm registry is disabled through the ini configuration, this method returns False.

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
            logger.debug("Support for the npm registry is disabled.")
            return False
        compatible_build_tool_classes = [NPM, Yarn]
        for build_tool_class in compatible_build_tool_classes:
            if isinstance(build_tool, build_tool_class):
                return True
        return False

    def download_attestation_payload(self, url: str, download_path: str) -> bool:
        """Download the npm attestation from npm registry.

        Each npm package has two types of attestations:

        * publish with "https://github.com/npm/attestation/tree/main/specs/publish/v0.1" predicateType
        * SLSA with "https://slsa.dev/provenance/v0.2" predicateType
        * SLSA with "https://slsa.dev/provenance/v1" predicateType

        For now we download the SLSA provenance v0.2 in this method.

        Here is an example SLSA v0.2 provenance: https://registry.npmjs.org/-/npm/v1/attestations/@sigstore/mock@0.1.0

        Parameters
        ----------
        url: str
            The attestation URL.
        download_path: str
            The download path for the asset.

        Returns
        -------
        bool
            ``True`` if the asset is downloaded successfully; ``False`` if not.

        Raises
        ------
        InvalidHTTPResponseError
            If the HTTP request to the registry fails or an unexpected response is returned.
        """
        response = send_get_http_raw(url, headers=None, timeout=self.request_timeout)
        if not response or response.status_code != 200:
            logger.debug("Unable to find attestation at %s", url)
            return False
        try:
            res_obj = response.json()
        except requests.exceptions.JSONDecodeError as error:
            raise InvalidHTTPResponseError(f"Failed to process response from npm for {url}.") from error
        if not res_obj:
            raise InvalidHTTPResponseError(f"Empty response returned by {url} .")
        if not res_obj.get("attestations"):
            raise InvalidHTTPResponseError(f"The response returned by {url} misses `attestations` attribute.")

        # Download the SLSA provenance only.
        for att in res_obj.get("attestations"):
            if not att.get("predicateType"):
                logger.debug("predicateType attribute is missing for %s", url)
                continue
            if att.get("predicateType") != "https://slsa.dev/provenance/v0.2":
                logger.debug("predicateType %s is not accepted. Skipping...", att.get("predicateType"))
                continue
            if not (bundle := att.get("bundle")):
                logger.debug("bundle attribute in the attestation is missing. Skipping...")
                continue
            if not (dsse_env := bundle.get("dsseEnvelope")):
                logger.debug("dsseEnvelope attribute in the bundle is missing. Skipping...")
                continue

            try:
                with open(download_path, "w", encoding="utf-8") as file:
                    json.dump(dsse_env, file)
                    return True
            except OSError as error:
                logger.debug(
                    "Failed to write the downloaded attestation from %s to %s. Error: %s",
                    url,
                    download_path,
                    error,
                )

        return False


class NPMAttestationAsset(NamedTuple):
    """An attestation asset hosted on the npm registry.

    The API Documentation can be found here:
    """

    #: The optional scope of a package on npm, which is used as the namespace in a PURL string.
    #: See https://docs.npmjs.com/cli/v10/using-npm/scope to know about npm scopes.
    #: See https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst#npm for the namespace in an npm PURL string.
    namespace: str | None

    #: The artifact ID.
    artifact_id: str

    #: The version of the asset.
    version: str

    #: The npm registry.
    npm_registry: NPMRegistry

    #: The size of the asset (in bytes). This attribute is added to match the AssetLocator
    #: protocol and is not used because npm API registry does not provide it.
    size_in_bytes: int

    @property
    def name(self) -> str:
        """Get the asset name."""
        return self.artifact_id

    @property
    def url(self) -> str:
        """Get the download URL of the asset.

        Note: we assume that the path parameters used to construct the URL are sanitized already.

        Returns
        -------
        str
        """
        # Build the path parameters.
        path_params = [self.npm_registry.attestation_endpoint]
        if self.namespace:
            path_params.append(self.namespace)
        path_params.append(self.artifact_id)
        path = "/".join(path_params)

        # Check that version is not an empty string.
        if self.version:
            path = f"{path}@{self.version}"

        return urlunsplit(
            SplitResult(
                scheme="https",
                netloc=self.npm_registry.hostname,
                path=path,
                query="",
                fragment="",
            )
        )

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
        try:
            return self.npm_registry.download_attestation_payload(self.url, dest)
        except InvalidHTTPResponseError as error:
            logger.debug(error)
            return False
