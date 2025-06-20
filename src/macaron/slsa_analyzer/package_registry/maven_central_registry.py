# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The module provides abstractions for the Maven Central package registry."""
import hashlib
import logging
import urllib.parse
from datetime import datetime, timezone

import requests
from packageurl import PackageURL
from requests import RequestException

from macaron.artifact.maven import construct_maven_repository_path, construct_primary_jar_file_name
from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError, InvalidHTTPResponseError
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
        super().__init__("Maven Central Registry", {"maven", "gradle"})

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

        self.search_netloc = section.get("search_netloc", "")
        if not self.search_netloc:
            raise ConfigurationError(
                f'The "search_netloc" key is missing in section [{section_name}] of the .ini configuration file.'
            )

        self.search_scheme = section.get("search_scheme", "https")
        self.search_endpoint = section.get("search_endpoint", "")
        if not self.search_endpoint:
            raise ConfigurationError(
                f'The "search_endpoint" key is missing in section [{section_name}] of the .ini configuration file.'
            )

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

        try:
            self.request_timeout = section.getint("request_timeout", fallback=10)
        except ValueError as error:
            raise ConfigurationError(
                f'The "request_timeout" value in section [{section_name}]'
                f"of the .ini configuration file is invalid: {error}",
            ) from error

    def find_publish_timestamp(self, purl: str) -> datetime:
        """Make a search request to Maven Central to find the publishing timestamp of an artifact.

        The reason for directly fetching timestamps from Maven Central is that deps.dev occasionally
        misses timestamps for Maven artifacts, making it unreliable for this purpose.

        To see the search API syntax see: https://central.sonatype.org/search/rest-api-guide/

        Parameters
        ----------
        purl: str
            The Package URL (purl) of the package whose publication timestamp is to be retrieved.
            This should conform to the PURL specification.

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

        if not purl_object.version:
            raise InvalidHTTPResponseError("The PackageURL of the software component misses version.")

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
        if response:
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

    def get_artifact_hash(self, purl: PackageURL) -> str | None:
        """Return the hash of the artifact found by the passed purl relevant to the registry's URL.

        An artifact's URL will be as follows:
        {registry_url}/{artifact_path}/{file_name}
        Where:
        - {registry_url} is determined by the setup/config of the registry.
        - {artifact_path} is determined by the Maven repository layout.
        (See: https://maven.apache.org/repository/layout.html and
        https://maven.apache.org/guides/mini/guide-naming-conventions.html)
        - {file_name} is {purl.name}-{purl.version}.jar (For a JAR artefact)

        Example
        -------
        PURL: pkg:maven/com.experlog/xapool@1.5.0
         URL: https://repo1.maven.org/maven2/com/experlog/xapool/1.5.0/xapool-1.5.0.jar

        Parameters
        ----------
        purl: PackageURL
            The purl of the artifact.

        Returns
        -------
        str | None
            The hash of the artifact, or None if not found.
        """
        if not purl.namespace:
            return None

        file_name = construct_primary_jar_file_name(purl)
        if not (purl.version and file_name):
            return None

        # Maven supports but does not require a sha256 hash of uploaded artifacts.
        artifact_path = construct_maven_repository_path(purl.namespace, purl.name, purl.version)
        artifact_url = self.registry_url + "/" + artifact_path + "/" + file_name
        artifact_sha256_url = artifact_url + ".sha256"
        logger.debug("Search for artifact hash using URL: %s", [artifact_sha256_url, artifact_url])

        response = send_get_http_raw(artifact_sha256_url, {})
        retrieved_artifact_hash = None
        if response and (retrieved_artifact_hash := response.text):
            # As Maven hashes are user provided and not verified they serve as a reference only.
            logger.debug("Found hash of artifact: %s", retrieved_artifact_hash)

        try:
            response = requests.get(artifact_url, stream=True, timeout=40)
            response.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            logger.debug("HTTP error occurred when trying to download artifact: %s", http_err)
            return None

        if response.status_code != 200:
            return None

        # Download file and compute hash as chunks are received.
        hash_algorithm = hashlib.sha256()
        try:
            for chunk in response.iter_content():
                hash_algorithm.update(chunk)
        except RequestException as error:
            # Something went wrong with the request, abort.
            logger.debug("Error while streaming target file: %s", error)
            response.close()
            return None

        computed_artifact_hash: str = hash_algorithm.hexdigest()
        if retrieved_artifact_hash and computed_artifact_hash != retrieved_artifact_hash:
            logger.debug(
                "Artifact hash and discovered hash do not match: %s != %s",
                computed_artifact_hash,
                retrieved_artifact_hash,
            )
            return None

        logger.debug("Computed hash of artifact: %s", computed_artifact_hash)
        return computed_artifact_hash
