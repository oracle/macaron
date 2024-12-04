# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module declares types and utilities for handling local artifacts."""

import fnmatch
import glob
import os
from collections.abc import Mapping

from packageurl import PackageURL

from macaron.artifact.maven import construct_maven_repository_path


def construct_local_artifact_paths_glob_pattern_maven_purl(maven_purl: PackageURL) -> list[str] | None:
    """Return a list of glob pattern(s) representing maven artifacts in a local maven repository.

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
    >>> construct_local_artifact_paths_glob_pattern_maven_purl(purl)
    ['com/oracle/macaron/macaron/0.13.0']
    """
    if not maven_purl.type == "maven":
        return None

    group = maven_purl.namespace
    artifact = maven_purl.name
    version = maven_purl.version

    if group is None or version is None:
        return None

    return [construct_maven_repository_path(group, artifact, version)]


def construct_local_artifact_paths_glob_pattern_pypi_purl(pypi_purl: PackageURL) -> list[str] | None:
    """Return a list of glob pattern(s) representing python artifacts in a virtual environment.

    The glob pattern(s) can be used to search in `<...>/<python_venv>/lib/python3.x/site-packages`
    directory.

    Parameters
    ----------
    maven_purl : PackageURL
        A pypi type PackageURL instance.

    Returns
    -------
    list[str] | None
        A list of glob patterns or None if an error happened.

    Examples
    --------
    >>> from packageurl import PackageURL
    >>> purl = PackageURL.from_string("pkg:pypi/django@1.11.1")
    >>> construct_local_artifact_paths_glob_pattern_pypi_purl(purl)
    ['django', 'django-1.11.1.dist-info', 'django-1.11.1.data']
    """
    if not pypi_purl.type == "pypi":
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


def find_artifact_paths_from_local_maven_repo(
    local_maven_repo: str,
    glob_patterns: list[str],
) -> list[str] | None:
    """Find maven artifacts within a local maven repository directory.

    ``local_maven_repo`` should be in format `<...>/.m2/repository`.

    Parameters
    ----------
    local_maven_repo: str
        The path to the directories to find artifacts.
    glob_patterns: list[str]
        The list of glob patterns that matches to artifact file names.

    Returns
    -------
    list[str] | None
        The list of path to found artifacts in the form of ``local_maven_repo``/<artifact_specific_path>
    """
    if not os.path.isdir(local_maven_repo):
        return None

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


def find_artifact_paths_from_python_venv(
    venv_path: str,
    glob_patterns: list[str],
) -> list[str] | None:
    """Find python artifacts within a python virtual environment directory.

    For packages in the virtual environment, we will treat their name case-insensitively.
    https://packaging.python.org/en/latest/specifications/name-normalization/

    Parameters
    ----------
    local_maven_repo: str
        The path to the directories to find artifacts.
    glob_patterns: list[str]
        The list of glob patterns that matches to artifact file names.

    Returns
    -------
    list[str] | None
        The list of path to found artifacts in the form of ``local_maven_repo``/<artifact_specific_path>
    """
    if not os.path.isdir(venv_path):
        return None

    artifact_paths = []

    try:
        venv_path_entries = os.listdir(venv_path)
    except (NotADirectoryError, PermissionError, FileNotFoundError):
        return None

    all_package_dirs: list[str] = []
    for entry in venv_path_entries:
        entry_path = os.path.join(venv_path, entry)
        if os.path.isdir(entry_path):
            all_package_dirs.append(entry)

    for package_dir in all_package_dirs:
        for pattern in glob_patterns:
            if fnmatch.fnmatch(package_dir.lower(), pattern.lower()):
                full_path = os.path.join(venv_path, package_dir)
                artifact_paths.append(full_path)

    return artifact_paths


def _get_local_artifact_path_for_build_tool_purl_type(
    purl: PackageURL,
    build_tool_purl_type: str,
    local_artifact_repo: str,
) -> list[str] | None:
    """Find local artifacts within ``local_artifact_repo`` depending on the purl type."""
    if build_tool_purl_type == "maven":
        maven_artifact_patterns = construct_local_artifact_paths_glob_pattern_maven_purl(purl)
        if not maven_artifact_patterns:
            return None

        artifact_paths = find_artifact_paths_from_local_maven_repo(
            local_maven_repo=local_artifact_repo,
            glob_patterns=maven_artifact_patterns,
        )

        if artifact_paths:
            return artifact_paths

    if build_tool_purl_type == "pypi":
        pypi_artifact_patterns = construct_local_artifact_paths_glob_pattern_pypi_purl(purl)
        if not pypi_artifact_patterns:
            return None

        artifact_paths = find_artifact_paths_from_python_venv(
            venv_path=local_artifact_repo,
            glob_patterns=pypi_artifact_patterns,
        )

        if artifact_paths:
            return artifact_paths

    return None


def get_local_artifact_paths(
    purl: PackageURL,
    build_tool_purl_types: list[str],
    local_artifact_repo_mapper: Mapping[str, str],
) -> dict[str, list[str]]:
    """Return the path to local artifacts for a PackageURL.

    We look for local artifacts of this PURL in all local repos corresponding to each purl
    type in ``build_tool_purl_types`` (e.g a pypi build tool type will map to the python virtual
    environment, if available).

    This function returns a dictionary with:
    - keys: The purl type
    - values: The list of aritfact paths corresponding to a purl type

    If a key doesn't exist, we cannot construct the artifact paths for that purl type. This can
    happen because of:
    - no local artifact repo found or given from user OR
    - not enough information from PURL type OR
    - build PURL type is not supported OR
    - no valid artifact paths found

    We assume that all paths in ``local_artifact_repo_mapper`` exist.

    Parameters
    ----------
    purl : PackageURL
        The purl we want to find local artifacts
    build_tool_purl_types : list[str]
        The list of build tool purl type to look for local artifacts.
    local_artifact_repo_mapper: Mapping[str, str]
        The mapping between each build purl type and the local artifact repo directory.

    Returns
    -------
    dict[str, list[str]]
        A mapping between build purl type and the paths to local artifacts if found.
    """
    result = {}

    for build_tool_purl_type in build_tool_purl_types:
        local_artifact_repo = local_artifact_repo_mapper.get(build_tool_purl_type)
        if not local_artifact_repo:
            continue

        # ``local_artifact_repo`` here correspond to ``build_tool_purl_type`` already
        # However, because for each build tool purl type, we have different ways of:
        # - Generating glob patterns
        # - Applying the glob patterns
        # I still put ``local_artifact_repo`` in _get_local_artifact_path_for_build_tool_purl_type
        # to further handle those tasks.
        artifact_paths = _get_local_artifact_path_for_build_tool_purl_type(
            purl=purl,
            build_tool_purl_type=build_tool_purl_type,
            local_artifact_repo=local_artifact_repo,
        )

        if not artifact_paths:
            continue

        result[build_tool_purl_type] = artifact_paths

    return result
