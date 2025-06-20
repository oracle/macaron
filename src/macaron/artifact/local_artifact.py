# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module declares types and utilities for handling local artifacts."""

import fnmatch
import glob
import hashlib
import logging
import os

from packageurl import PackageURL

from macaron.artifact.maven import construct_maven_repository_path, construct_primary_jar_file_name
from macaron.errors import LocalArtifactFinderError

logger: logging.Logger = logging.getLogger(__name__)


def construct_local_artifact_dirs_glob_pattern_maven_purl(maven_purl: PackageURL) -> list[str] | None:
    """Return a list of glob pattern(s) representing the directory that contains the local maven artifacts for ``maven_purl``.

    The glob pattern(s) can be used to search in `<...>/.m2/repository` directory.

    Parameters
    ----------
    maven_purl : PackageURL
        A maven type PackageURL instance.

    Returns
    -------
    list[str] | None
        A list of glob patterns or None if an error happened.

    Examples
    --------
    >>> from packageurl import PackageURL
    >>> purl = PackageURL.from_string("pkg:maven/com.oracle.macaron/macaron@0.13.0")
    >>> construct_local_artifact_dirs_glob_pattern_maven_purl(purl)
    ['com/oracle/macaron/macaron/0.13.0']
    """
    if maven_purl.type != "maven":
        return None

    group = maven_purl.namespace
    artifact = maven_purl.name
    version = maven_purl.version

    if group is None or version is None:
        return None

    return [construct_maven_repository_path(group, artifact, version)]


def construct_local_artifact_dirs_glob_pattern_pypi_purl(pypi_purl: PackageURL) -> list[str] | None:
    """Return a list of glob pattern(s) representing directories that contains the artifacts in a Python virtual environment.

    The glob pattern(s) can be used to search in `<...>/<python_venv>/lib/python3.x/site-packages`
    directory.

    Parameters
    ----------
    pypi_purl : PackageURL
        A pypi type PackageURL instance.

    Returns
    -------
    list[str] | None
        A list of glob patterns or None if an error happened.

    Examples
    --------
    >>> from packageurl import PackageURL
    >>> purl = PackageURL.from_string("pkg:pypi/django@1.11.1")
    >>> construct_local_artifact_dirs_glob_pattern_pypi_purl(purl)
    ['django', 'django-1.11.1.dist-info', 'django-1.11.1.data']
    """
    if pypi_purl.type != "pypi":
        return None

    name = pypi_purl.name
    version = pypi_purl.version

    if version is None:
        return None

    # These patterns are from the content of a wheel file, which are extracted into the site-packages
    # directory. References:
    # https://packaging.python.org/en/latest/specifications/binary-distribution-format/#file-contents
    glob_patterns = []
    glob_patterns.append(name)
    glob_patterns.append(f"{name}-{version}.dist-info")
    glob_patterns.append(f"{name}-{version}.data")

    return glob_patterns


def find_artifact_dirs_from_local_maven_repo(
    local_maven_repo: str,
    glob_patterns: list[str],
) -> list[str]:
    """Find directories that contains maven artifacts within a maven local repository.

    ``local_maven_repo`` should be in format `<...>/.m2/repository`.

    Parameters
    ----------
    local_maven_repo: str
        The path to the directory to find artifacts.
    glob_patterns: list[str]
        The list of glob patterns that matches to artifact directory names.

    Returns
    -------
    list[str]
        The list of paths to artifact directories in the form of ``venv_site_package_path``/path/to/artifact_dir
        If no artifact directory is found, this list will be empty.

    Raises
    ------
    LocalArtifactFinderError
        If ``local_maven_repo`` doesn't exist.
    """
    if not os.path.isdir(local_maven_repo):
        raise LocalArtifactFinderError(f"{local_maven_repo} doesn't exist.")

    artifact_paths = []
    for pattern in glob_patterns:
        found_paths = glob.glob(
            root_dir=local_maven_repo,
            pathname=pattern,
        )

        for found_path in found_paths:
            full_path = os.path.join(local_maven_repo, found_path)
            if os.path.isdir(full_path):
                artifact_paths.append(full_path)

    return artifact_paths


def find_artifact_dirs_from_python_venv(
    venv_site_package_path: str,
    glob_patterns: list[str],
) -> list[str]:
    """Find directories within a python virtual environment.

    For packages in the virtual environment, we will treat their name case-insensitively.
    https://packaging.python.org/en/latest/specifications/name-normalization/

    ``venv_site_package_path`` should be in format `<...>/lib/python3.*/site-packages/`.

    Parameters
    ----------
    venv_path: str
        The path to the local directory to find artifacts.
    glob_patterns: list[str]
        The list of glob patterns that matches to artifact directory names.

    Returns
    -------
    list[str]
        The list of paths to artifact directories in the form of ``venv_site_package_path``/path/to/artifact_dir
        If no artifact directory is found, this list will be empty.

    Raises
    ------
    LocalArtifactFinderError
        If ``venv_site_package_path`` doesn't exist or if we cannot view the sub-directory of it.
    """
    if not os.path.isdir(venv_site_package_path):
        raise LocalArtifactFinderError(f"{venv_site_package_path} doesn't exist.")

    artifact_paths = []

    try:
        venv_path_entries = os.listdir(venv_site_package_path)
    except (NotADirectoryError, PermissionError, FileNotFoundError) as error:
        error_msg = f"Cannot view the sub-directory of venv {venv_site_package_path}"
        raise LocalArtifactFinderError(error_msg) from error

    all_package_dirs: list[str] = []
    for entry in venv_path_entries:
        entry_path = os.path.join(venv_site_package_path, entry)
        if os.path.isdir(entry_path):
            all_package_dirs.append(entry)

    for package_dir in all_package_dirs:
        for pattern in glob_patterns:
            if fnmatch.fnmatch(package_dir.lower(), pattern.lower()):
                full_path = os.path.join(venv_site_package_path, package_dir)
                artifact_paths.append(full_path)

    return artifact_paths


def get_local_artifact_dirs(
    purl: PackageURL,
    local_artifact_repo_path: str,
) -> list[str]:
    """Return the paths to directories that store local artifacts for a PackageURL.

    We look for local artifacts of ``purl`` in ``local_artifact_repo_path``.

    This function returns a list of paths (as strings), each has the format
        ``local_artifact_repo_path``/path/to/artifact_dir``

    This will mean that no path to an artifact is returned. Therefore, it's the responsibility
    of this function caller to inspect the artifact directory to obtain the required
    artifact.

    We assume that ``local_artifact_repo_path`` exists.

    Parameters
    ----------
    purl : PackageURL
        The purl we want to find local artifacts
    local_artifact_repo_path : str
        The local artifact repo directory.

    Returns
    -------
    list[str]
        The list contains the artifact directory paths. It will be empty if no artifact can be found.

    Raises
    ------
    LocalArtifactFinderError
        If an error happens when looking for local artifacts.
    """
    purl_type = purl.type

    if purl_type == "maven":
        maven_artifact_patterns = construct_local_artifact_dirs_glob_pattern_maven_purl(purl)
        if not maven_artifact_patterns:
            raise LocalArtifactFinderError(f"Cannot generate maven artifact patterns for {purl}")

        return find_artifact_dirs_from_local_maven_repo(
            local_maven_repo=local_artifact_repo_path,
            glob_patterns=maven_artifact_patterns,
        )

    if purl_type == "pypi":
        pypi_artifact_patterns = construct_local_artifact_dirs_glob_pattern_pypi_purl(purl)
        if not pypi_artifact_patterns:
            raise LocalArtifactFinderError(f"Cannot generate Python package patterns for {purl}")

        return find_artifact_dirs_from_python_venv(
            venv_site_package_path=local_artifact_repo_path,
            glob_patterns=pypi_artifact_patterns,
        )

    raise LocalArtifactFinderError(f"Unsupported PURL type {purl_type}")


def get_local_artifact_hash(purl: PackageURL, artifact_dirs: list[str]) -> str | None:
    """Compute the hash of the local artifact.

    Parameters
    ----------
    purl: PackageURL
        The PURL of the artifact being sought.
    artifact_dirs: list[str]
        The list of directories that may contain the artifact file.

    Returns
    -------
    str | None
        The hash, or None if not found.
    """
    if not artifact_dirs:
        logger.debug("No artifact directories provided.")
        return None

    if not purl.version:
        logger.debug("PURL is missing version.")
        return None

    artifact_target = None
    if purl.type == "maven":
        artifact_target = construct_primary_jar_file_name(purl)

    # TODO add support for other PURL types here.
    # Other purl types can be easily supported if user provided artifacts are accepted from the command line.
    # See https://github.com/oracle/macaron/issues/498.

    if not artifact_target:
        logger.debug("PURL type not supported: %s", purl.type)
        return None

    for artifact_dir in artifact_dirs:
        full_path = os.path.join(artifact_dir, artifact_target)
        if not os.path.exists(full_path):
            continue

        with open(full_path, "rb") as file:
            try:
                hash_result = hashlib.file_digest(file, "sha256")
            except ValueError as error:
                logger.debug("Error while hashing file: %s", error)
                continue

            return hash_result.hexdigest()

    return None
