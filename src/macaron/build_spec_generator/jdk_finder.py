# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module includes the functions for obtaining JDK version from a Java artifact."""

import logging
import os
import tempfile
import urllib.parse
import zipfile
from enum import Enum

import requests

from macaron.artifact.maven import construct_maven_repository_path
from macaron.config.global_config import global_config
from macaron.errors import InvalidHTTPResponseError

logger: logging.Logger = logging.getLogger(__name__)


class JavaArtifactExt(str, Enum):
    """The extensions for Java artifacts."""

    JAR = ".jar"


class CacheStrategy(Enum):
    """The strategy for caching the downloaded artifacts for JDK version finding."""

    DISABLE = 0
    MAVEN_LAYOUT = 1


def download_file(url: str, dest: str) -> None:
    """Stream a file into a local destination.

    Parameters
    ----------
    url: str
        The URL of the file to stream from.
    dest: str
        The path to the destination file in the local file system. This path
        includes the file name.

    Raises
    ------
    InvalidHTTPResponseError
        If an error happens while streaming the file.
    OSError
        If the parent directory of ``dest`` doesn't exist.
    """
    response = requests.get(url=url, stream=True, timeout=40)

    if response.status_code != 200:
        raise InvalidHTTPResponseError(f"Cannot download java artifact file from {url}")

    with open(dest, "wb") as fd:
        try:
            for chunk in response.iter_content(chunk_size=128, decode_unicode=False):
                fd.write(chunk)
        except requests.RequestException as error:
            response.close()
            raise InvalidHTTPResponseError(f"Error while streaming java artifact file from {url}") from error


def join_remote_maven_repo_url(
    remote_maven_url: str,
    maven_repo_path: str,
) -> str:
    """Join the base remote maven URL with a maven repository path.

    Parameters
    ----------
    remote_maven_url: str
        The url to a remove maven layout repository.
        For example: https://repo1.maven.org/maven2
    maven_repo_path: str
        The maven repository path for a GAV coordinate or an artifact
        from the root of the remote maven layout repository.

    Returns
    -------
    str
        The joined path.

    Examples
    --------
    >>> remote_maven_repo = "https://repo1.maven.org/maven2"
    >>> artifact_path = "io/liftwizard/liftwizard-checkstyle/2.1.22/liftwizard-checkstyle-2.1.22.jar"
    >>> join_remote_maven_repo_url(remote_maven_repo, artifact_path)
    'https://repo1.maven.org/maven2/io/liftwizard/liftwizard-checkstyle/2.1.22/liftwizard-checkstyle-2.1.22.jar'
    >>> join_remote_maven_repo_url(remote_maven_repo, "io/liftwizard/liftwizard-checkstyle/2.1.22/")
    'https://repo1.maven.org/maven2/io/liftwizard/liftwizard-checkstyle/2.1.22/'
    >>> join_remote_maven_repo_url(f"{remote_maven_repo}/", artifact_path)
    'https://repo1.maven.org/maven2/io/liftwizard/liftwizard-checkstyle/2.1.22/liftwizard-checkstyle-2.1.22.jar'
    """
    url_parse_result = urllib.parse.urlparse(remote_maven_url)
    new_path_component = os.path.join(
        url_parse_result.path,
        maven_repo_path,
    )
    return urllib.parse.urlunparse(
        urllib.parse.ParseResult(
            scheme=url_parse_result.scheme,
            netloc=url_parse_result.netloc,
            path=new_path_component,
            params="",
            query="",
            fragment="",
        )
    )


def get_jdk_version_from_jar(artifact_path: str) -> str | None:
    """Return the JDK version obtained from a Java artifact.

    Parameters
    ----------
    artifact_path: str
        The path to the artifact to extract the jdk version.

    Returns
    -------
    str | None
        The version string extract from the artifact (as is) or None
        if there is an error, or if we couldn't find any jdk version.
    """
    with zipfile.ZipFile(artifact_path, "r") as jar:
        manifest_path = "META-INF/MANIFEST.MF"
        with jar.open(manifest_path) as manifest_file:
            manifest_content = manifest_file.read().decode("utf-8")
            for line in manifest_content.splitlines():
                if "Build-Jdk" in line or "Build-Jdk-Spec" in line:
                    _, _, version = line.rpartition(":")
                    logger.debug(
                        "Found JDK version %s from java artifact at %s",
                        version.strip(),
                        artifact_path,
                    )
                    return version.strip()

            logger.debug("Cannot find any JDK version from java artifact at %s", artifact_path)
            return None


def find_jdk_version_from_remote_maven_repo_standalone(
    group_id: str,
    artifact_id: str,
    version: str,
    asset_name: str,
    remote_maven_repo_url: str,
) -> str | None:
    """Return the jdk version string from an artifact matching a given GAV from a remote maven layout repository.

    This function doesn't cache the downloaded artifact, and remove it after the function exits.
    We assume that the remote maven layout repository supports downloading a file through a HTTPS URL.

    Parameters
    ----------
    group_id: str
        The group ID part of the GAV coordinate.
    artifact_id: str
        The artifact ID part of the GAV coordinate.
    version: str
        The version part of the GAV coordinate.
    asset_name: str
        The name of artifact to download and extract the jdk version.
    ext: JavaArtifactExt
        The extension of the main artifact file.
    remote_maven_repo_url: str
        The URL to the remote maven layout repository.

    Returns
    -------
    str | None
        The version string extract from the artifact (as is) or None
        ff there is an error, or if we couldn't find any jdk version.
    """
    maven_repository_path = construct_maven_repository_path(
        group_id=group_id,
        artifact_id=artifact_id,
        version=version,
        asset_name=asset_name,
    )

    artifact_url = join_remote_maven_repo_url(
        remote_maven_repo_url,
        maven_repository_path,
    )
    logger.debug(
        "Find JDK version from jar at %s, using temporary file.",
        artifact_url,
    )
    with tempfile.TemporaryDirectory() as temp_dir_name:
        local_artifact_path = os.path.join(temp_dir_name, asset_name)
        try:
            download_file(
                artifact_url,
                local_artifact_path,
            )
        except InvalidHTTPResponseError as error:
            logger.error("Failed why trying to download jar file. Error: %s", error)
            return None
        except OSError as os_error:
            logger.critical("Critical %s", os_error)
            return None

        return get_jdk_version_from_jar(local_artifact_path)


def find_jdk_version_from_remote_maven_repo_cache(
    group_id: str,
    artifact_id: str,
    version: str,
    asset_name: str,
    remote_maven_repo_url: str,
    local_cache_repo: str,
) -> str | None:
    """Return the jdk version string from an artifact matching a given GAV from a remote maven layout repository.

    This function cache the downloaded artifact in a maven layout https://maven.apache.org/repository/layout.html
    under ``local_cache_repo``.
    We assume that the remote maven layout repository supports downloading a file through a HTTPS URL.

    Parameters
    ----------
    group_id: str
        The group ID part of the GAV coordinate.
    artifact_id: str
        The artifact ID part of the GAV coordinate.
    version: str
        The version part of the GAV coordinate.
    asset_name: str
        The name of artifact to download and extract the jdk version.
    remote_maven_repo_url: str
        The URL to the remote maven layout repository.
    local_cache_repo: str
        The path to a local directory for caching the downloaded artifact used in JDK version
        extraction.

    Returns
    -------
    str | None
        The version string extract from the artifact (as is) or None
        ff there is an error, or if we couldn't find any jdk version.
    """
    maven_repository_path = construct_maven_repository_path(
        group_id=group_id,
        artifact_id=artifact_id,
        version=version,
        asset_name=asset_name,
    )

    local_artifact_path = os.path.join(
        local_cache_repo,
        maven_repository_path,
    )
    if os.path.isfile(local_artifact_path):
        return get_jdk_version_from_jar(local_artifact_path)

    gav_path = os.path.dirname(local_artifact_path)
    os.makedirs(
        gav_path,
        exist_ok=True,
    )

    artifact_url = join_remote_maven_repo_url(
        remote_maven_repo_url,
        maven_repository_path,
    )
    logger.debug(
        "Find JDK version from jar at %s, using cache %s",
        artifact_url,
        local_artifact_path,
    )
    try:
        download_file(
            artifact_url,
            local_artifact_path,
        )
    except InvalidHTTPResponseError as error:
        logger.error("Failed why trying to download jar file. Error: %s", error)
        return None
    except OSError as os_error:
        logger.critical("Critical %s", os_error)
        return None

    return get_jdk_version_from_jar(local_artifact_path)


def find_jdk_version_from_central_maven_repo(
    group_id: str,
    artifact_id: str,
    version: str,
    cache_strat: CacheStrategy = CacheStrategy.MAVEN_LAYOUT,
) -> str | None:
    """Return the jdk version string from an artifact matching a given GAV from Maven Central repository.

    The artifacts will be downloaded from https://repo1.maven.org/maven2/ for JDK version extraction.

    We now only support JAR files.

    Parameters
    ----------
    group_id: str
        The group ID part of the GAV coordinate.
    artifact_id: str
        The artifact ID part of the GAV coordinate.
    version: str
        The version part of the GAV coordinate.
    cache_strat: CacheStrategy
        Specify how artifacts from maven central are persisted.

    Returns
    -------
    str | None
        The version string extract from the artifact (as is) or None
        ff there is an error, or if we couldn't find any jdk version.
    """
    central_repo_url = "https://repo1.maven.org/maven2/"
    local_cache_maven_repo = os.path.join(
        global_config.output_path,
        "jdk_finding_cache_maven_repo",
    )
    asset_name = f"{artifact_id}-{version}{JavaArtifactExt.JAR.value}"

    match cache_strat:
        case CacheStrategy.MAVEN_LAYOUT:
            return find_jdk_version_from_remote_maven_repo_cache(
                group_id=group_id,
                artifact_id=artifact_id,
                version=version,
                asset_name=asset_name,
                remote_maven_repo_url=central_repo_url,
                local_cache_repo=local_cache_maven_repo,
            )
        case CacheStrategy.DISABLE:
            return find_jdk_version_from_remote_maven_repo_standalone(
                group_id=group_id,
                artifact_id=artifact_id,
                version=version,
                asset_name=asset_name,
                remote_maven_repo_url=central_repo_url,
            )
