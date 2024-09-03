# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The module provides abstractions for the Maven Central package registry."""

import logging
import urllib.parse
from datetime import datetime, timezone

import requests
from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError, InvalidHTTPResponseError
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.package_registry.package_registry import PackageRegistry
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)

# These are the code hosting platforms that are recognized by Sonatype for namespace verification in maven central.
RECOGNIZED_CODE_HOSTING_SERVICES = [
    "github",
    "gitlab",
    "bitbucket",
    "gitee",
]


def same_organization(group_id_1: str, group_id_2: str) -> bool:
    """Check if two maven group ids are from the same organization.

    Note: It is assumed that for recognized source platforms, the top level domain doesn't change the organization.
    I.e., io.github.foo and com.github.foo are assumed to be from the same organization.

    Parameters
    ----------
    group_id_1 : str
        The first group id.
    group_id_2 : str
        The second group id.

    Returns
    -------
    bool
        ``True`` if the two group ids are from the same organization, ``False`` otherwise.
    """
    if group_id_1 == group_id_2:
        return True

    group_id_1_parts = group_id_1.split(".")
    group_id_2_parts = group_id_2.split(".")
    if min(len(group_id_1_parts), len(group_id_2_parts)) < 2:
        return False

    # For groups ids that are under recognized maven namespaces, we only compare the first 3 parts.
    # For example, io.github.foo.bar and io.github.foo are from the same organization (foo).
    # Also, io.github.foo and com.github.foo are from the same organization.
    if (
        group_id_1_parts[0] in {"io", "com"}
        and group_id_1_parts[1] in RECOGNIZED_CODE_HOSTING_SERVICES
        and group_id_2_parts[0] in {"io", "com"}
        and group_id_2_parts[1] in RECOGNIZED_CODE_HOSTING_SERVICES
    ):
        if len(group_id_1_parts) >= 3 and len(group_id_2_parts) >= 3:
            return group_id_1_parts[2] == group_id_2_parts[2]
        return False

    return all(group_id_1_parts[index] == group_id_2_parts[index] for index in range(2))


class MavenCentralRegistry(PackageRegistry):
    """This class implements a Maven Central package registry."""

    def __init__(
        self,
        search_netloc: str | None = None,
        search_scheme: str | None = None,
        search_endpoint: str | None = None,
        registry_url_netloc: str | None = None,
        registry_url_scheme: str | None = None,
        request_timeout: int | None = None,
    ) -> None:
        """
        Initialize a Maven Central Registry instance.

        Parameters
        ----------
        search_netloc: str | None = None,
            The netloc of Maven Central search URL.
        search_scheme: str | None = None,
            The scheme of Maven Central URL.
        search_endpoint : str | None
            The search REST API to find artifacts.
        registry_url_netloc: str | None
            The netloc of the Maven Central registry url.
        registry_url_scheme: str | None
            The scheme of the Maven Central registry url.
        request_timeout : int | None
            The timeout (in seconds) for requests made to the package registry.
        """
        self.search_netloc = search_netloc or ""
        self.search_scheme = search_scheme or ""
        self.search_endpoint = search_endpoint or ""
        self.registry_url_netloc = registry_url_netloc or ""
        self.registry_url_scheme = registry_url_scheme or ""
        self.registry_url = ""  # Created from the registry_url_scheme and registry_url_netloc.
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

        self.search_netloc = section.get("search_netloc")
        if not self.search_netloc:
            raise ConfigurationError(
                f'The "search_netloc" key is missing in section [{section_name}] of the .ini configuration file.'
            )

        self.search_scheme = section.get("search_scheme", "https")
        self.search_endpoint = section.get("search_endpoint")
        if not self.search_endpoint:
            raise ConfigurationError(
                f'The "search_endpoint" key is missing in section [{section_name}] of the .ini configuration file.'
            )

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
        return any(isinstance(build_tool, build_tool_class) for build_tool_class in compatible_build_tool_classes)

    def find_publish_timestamp(self, purl: str, registry_url: str | None = None) -> datetime:
        """Make a search request to Maven Central to find the publishing timestamp of an artifact.

        The reason for directly fetching timestamps from Maven Central is that deps.dev occasionally
        misses timestamps for Maven artifacts, making it unreliable for this purpose.

        To see the search API syntax see: https://central.sonatype.org/search/rest-api-guide/

        Parameters
        ----------
        purl: str
            The Package URL (purl) of the package whose publication timestamp is to be retrieved.
            This should conform to the PURL specification.
        registry_url: str | None
            The registry URL that can be set for testing.

        Returns
        -------
        datetime
            A timezone-aware datetime object representing the publication timestamp
            of the specified package.

        Raises
        ------
        InvalidHTTPResponseError
            If the URL construction fails, the HTTP response is invalid, or if the response
            cannot be parsed correctly, or if the expected timestamp is missing or invalid.
        """
        try:
            purl_object = PackageURL.from_string(purl)
        except ValueError as error:
            logger.debug("Could not parse PURL: %s", error)
        query_params = [f"q=g:{purl_object.namespace}", f"a:{purl_object.name}", f"v:{purl_object.version}"]

        try:
            url = urllib.parse.urlunsplit(
                urllib.parse.SplitResult(
                    scheme=self.search_scheme,
                    netloc=self.search_netloc,
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
                return datetime.fromtimestamp(round(timestamp / 1000), tz=timezone.utc)
            except (OverflowError, OSError) as error:
                raise InvalidHTTPResponseError(f"The timestamp returned by {url} is invalid") from error

        raise InvalidHTTPResponseError(f"Invalid response from Maven central for {url}.")
