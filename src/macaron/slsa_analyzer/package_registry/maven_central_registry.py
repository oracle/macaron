# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The module provides abstractions for the Maven Central package registry."""

import logging
from datetime import datetime, timezone
from urllib.parse import SplitResult, urlunsplit

import requests

from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError, InvalidHTTPResponseError
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.package_registry.package_registry import PackageRegistry
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class MavenCentralRegistry(PackageRegistry):
    """This class implements a Maven Central package registry."""

    def __init__(
        self,
        hostname: str | None = None,
        search_endpoint: str | None = None,
        request_timeout: int | None = None,
    ) -> None:
        """
        Initialize a Maven Central Registry instance.

        Parameters
        ----------
        hostname : str
            The hostname of the Maven Central service.
        search_endpoint : str | None
            The search REST API to find artifacts.
        request_timeout : int | None
            The timeout (in seconds) for requests made to the package registry.
        """
        self.hostname = hostname or ""
        self.search_endpoint = search_endpoint or ""
        self.request_timeout = request_timeout or 10
        super().__init__("Maven Central Registry")

    def load_defaults(self) -> None:
        """Load the .ini configuration for the current package registry.

        Raises
        ------
        ConfigurationError
            If there is a schema violation in the ``maven_central`` section.
        """
        section_name = "package_registry.maven_central"
        if not defaults.has_section(section_name):
            return
        section = defaults[section_name]

        self.hostname = section.get("hostname")
        if not self.hostname:
            raise ConfigurationError(
                f'The "hostname" key is missing in section [{section_name}] of the .ini configuration file.'
            )

        self.search_endpoint = section.get("search_endpoint")
        if not self.search_endpoint:
            raise ConfigurationError(
                f'The "search_endpoint" key is missing in section [{section_name}] of the .ini configuration file.'
            )

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

        ``MavenCentralRegistry`` is compatible with Maven and Gradle.

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
        compatible_build_tool_classes = [Maven, Gradle]
        for build_tool_class in compatible_build_tool_classes:
            if isinstance(build_tool, build_tool_class):
                return True
        return False

    def find_publish_timestamp(self, group_id: str, artifact_id: str, version: str | None = None) -> datetime:
        """Make a search request to Maven Central to find the publishing timestamp of an artifact.

        If version is not provided, the timestamp of the latest version will be returned.

        To see the search API syntax see: https://central.sonatype.org/search/rest-api-guide/

        Parameters
        ----------
        group_id : str
            The group id of the artifact.
        artifact_id: str
            The artifact id of the artifact.
        version: str | None
            The version of the artifact.

        Returns
        -------
        datetime
            The artifact publish timestamp as a timezone-aware datetime object.

        Raises
        ------
        InvalidHTTPResponseError
            If the HTTP response is invalid or unexpected.
        """
        query_params = [f"q=g:{group_id}", f"a:{artifact_id}"]
        if version:
            query_params.append(f"v:{version}")

        try:
            url = urlunsplit(
                SplitResult(
                    scheme="https",
                    netloc=self.hostname,
                    path=f"/{self.search_endpoint}",
                    query="&".join(["+AND+".join(query_params), "core=gav", "rows=1", "wt=json"]),
                    fragment="",
                )
            )
        except ValueError as error:
            raise InvalidHTTPResponseError("Failed to construct the search URL for Maven Central.") from error

        response = send_get_http_raw(url, headers=None, timeout=self.request_timeout)
        if response and response.status_code == 200:
            try:
                res_obj = response.json()
            except requests.exceptions.JSONDecodeError as error:
                raise InvalidHTTPResponseError(f"Failed to process response from Maven central for {url}.") from error
            if not res_obj:
                raise InvalidHTTPResponseError(f"Empty response returned by {url} .")
            if not res_obj.get("response"):
                raise InvalidHTTPResponseError(f"The response returned by {url} misses `response` attribute.")
            if not res_obj.get("response").get("docs"):
                logger.debug("Failed to find the artifact at Maven central: %s.", url)
                raise InvalidHTTPResponseError(
                    f"The response returned by {url} misses `response.docs` attribute or it is empty."
                )

            # We only consider the first ``docs`` element.
            timestamp = res_obj.get("response").get("docs")[0].get("timestamp")
            if not timestamp:
                raise InvalidHTTPResponseError(f"The timestamp is missing in the response returned by {url}.")

            logger.debug("Found timestamp: %s.", timestamp)

            # The timestamp published in Maven Central is in milliseconds and needs to be divided by 1000.
            # Unfortunately, this is not documented in the API docs.
            try:
                return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            except (OverflowError, OSError) as error:
                raise InvalidHTTPResponseError(f"The timestamp returned by {url} is invalid") from error

        raise InvalidHTTPResponseError(f"Invalid response from Maven central for {url}.")
