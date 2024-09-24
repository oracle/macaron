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
    """Return a list of glob pattern(s) to be search in a maven layout local repo for artifact directories.

    Parameters
    ----------
    maven_purl : PackageURL
        A maven type PackageURL instance (e.g. `PackageURL.from_string("pkg:maven/com.oracle.macaron/macaron@0.13.0)`)

    Returns
    -------
    list[str] | None
        A list of glob patterns or None if an error happened.
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
    """Return a list of glob pattern(s) to be search in a Python virtual environment for artifact directories.

    Parameters
    ----------
    maven_purl : PackageURL
        A maven type PackageURL instance (e.g. `PackageURL.from_string("pkg:maven/com.oracle.macaron/macaron@0.13.0)`)

    Returns
    -------
    list[str] | None
        A list of glob patterns or None if an error happened.
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
    """Return a list of existed directories within `local_maven_repo`.

    Each directory path has the form ``local_maven_repo``/<artifact_specific_path>.

    None means error.
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


# Assume that local_python_venv exists.
# In here we need to do it case-insensitively
# We also assume that packages are just one level down from venv_path
# The return element are relative paths from venv.
def find_artifact_paths_from_python_venv(
    venv_path: str,
    glob_patterns: list[str],
) -> list[str] | None:
    """TBD."""
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
    """TBD."""
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


# key: purl type
# value: list of paths
# If a key doesn't exist -> cannot construct the artifact paths for that purl type
# (no local artifact repo found or not enough information from PURL type is not supported) OR no valid artifact paths found.
# We assume that the paths in local_artifact_repo_mapper all exists/
def get_local_artifact_paths(
    purl: PackageURL,
    build_tool_purl_types: list[str],
    local_artifact_repo_mapper: Mapping[str, str],
) -> dict[str, list[str]]:
    """Get C."""
    local_artifact_paths_purl_mapping = {}

    for build_tool_purl_type in build_tool_purl_types:
        local_artifact_repo = local_artifact_repo_mapper.get(build_tool_purl_type)
        if not local_artifact_repo:
            continue

        artifact_paths = _get_local_artifact_path_for_build_tool_purl_type(
            purl=purl,
            build_tool_purl_type=build_tool_purl_type,
            local_artifact_repo=local_artifact_repo,
        )

        if not artifact_paths:
            continue

        local_artifact_paths_purl_mapping[build_tool_purl_type] = artifact_paths

    return local_artifact_paths_purl_mapping
