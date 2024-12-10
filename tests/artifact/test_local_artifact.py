# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Test the local artifact utilities."""

import os
from pathlib import Path

import pytest
from packageurl import PackageURL

from macaron.artifact.local_artifact import (
    construct_local_artifact_paths_glob_pattern_maven_purl,
    construct_local_artifact_paths_glob_pattern_pypi_purl,
    find_artifact_paths_from_python_venv,
    get_local_artifact_paths,
)


@pytest.mark.parametrize(
    ("purl_str", "expectation"),
    [
        pytest.param(
            "pkg:maven/com.google.guava/guava@33.2.1-jre",
            ["com/google/guava/guava/33.2.1-jre"],
            id="A Maven PURL with group, artifact and version",
        ),
        pytest.param(
            "pkg:maven/com.google.guava/guava@33.2.1-jre?type=jar",
            ["com/google/guava/guava/33.2.1-jre"],
            id="A Maven PURL with group artifact, version and type qualifier",
        ),
    ],
)
def test_construct_local_artifact_paths_glob_pattern_maven_purl(
    purl_str: str,
    expectation: list[str],
) -> None:
    """Test constructing a local artifact patterns from a given maven purl."""
    maven_purl = PackageURL.from_string(purl_str)
    result = construct_local_artifact_paths_glob_pattern_maven_purl(maven_purl=maven_purl)
    assert result is not None
    assert sorted(result) == sorted(expectation)


@pytest.mark.parametrize(
    ("purl_str"),
    [
        pytest.param("pkg:pypi/django@5.0.6", id="The purl type is not supported."),
        pytest.param("pkg:maven/guava@33.2.1-jre", id="Missing group id in the PURL"),
        pytest.param("pkg:maven/guava", id="Missing version"),
    ],
)
def test_construct_local_artifact_paths_glob_pattern_maven_purl_error(purl_str: str) -> None:
    """Test constructing a local artifact patterns from a given maven purl with error."""
    maven_purl = PackageURL.from_string(purl_str)
    result = construct_local_artifact_paths_glob_pattern_maven_purl(maven_purl=maven_purl)
    assert result is None


@pytest.mark.parametrize(
    ("purl_str", "expectation"),
    [
        pytest.param(
            "pkg:pypi/django@5.0.6",
            ["django", "django-5.0.6.dist-info", "django-5.0.6.data"],
            id="A valid pypi PURL with version",
        )
    ],
)
def test_construct_local_artifact_paths_glob_pattern_pypi_purl(
    purl_str: str,
    expectation: list[str],
) -> None:
    """Test constructing a local artifact patterns from a given pypi purl."""
    pypi_purl = PackageURL.from_string(purl_str)
    result = construct_local_artifact_paths_glob_pattern_pypi_purl(pypi_purl=pypi_purl)
    assert result is not None
    assert sorted(result) == sorted(expectation)


@pytest.mark.parametrize(
    ("purl_str"),
    [
        pytest.param(
            "pkg:pypi/django",
            id="A pypi PURL without version",
        ),
        pytest.param(
            "pkg:maven/com.google.guava/guava@33.2.1-jre",
            id="The purl type is not supported.",
        ),
    ],
)
def test_construct_local_artifact_paths_glob_pattern_pypi_purl_error(purl_str: str) -> None:
    """Test constructing a local artifact patterns from a given pypi purl with error."""
    pypi_purl = PackageURL.from_string(purl_str)
    result = construct_local_artifact_paths_glob_pattern_pypi_purl(pypi_purl=pypi_purl)
    assert result is None


def test_find_artifact_paths_from_invalid_python_venv() -> None:
    """Test find_artifact_paths_from_python_venv method with invalid venv path"""
    assert not find_artifact_paths_from_python_venv("./does-not-exist", ["django", "django-5.0.6.dist-info"])


@pytest.mark.parametrize(
    ("purl_str", "build_tool_purl_types", "local_artifact_repo_mapper", "expectation"),
    [
        pytest.param(
            "pkg:maven/com.google.guava/guava@33.2.1-jre",
            ["maven", "pypi"],
            {},
            {},
            id="A maven type PURL where multiple build tool types are discovered. But no local repository is available.",
        ),
        pytest.param(
            "pkg:maven/com.google.guava/guava@33.2.1-jre",
            [],
            {},
            {},
            id="A maven type PURL where no build tool types are discovered and no local repository is available.",
        ),
    ],
)
def test_get_local_artifact_paths_empty(
    purl_str: str,
    build_tool_purl_types: list[str],
    local_artifact_repo_mapper: dict[str, str],
    expectation: dict[str, list[str]],
) -> None:
    """Test getting local artifact paths where the result is empty."""
    purl = PackageURL.from_string(purl_str)
    assert (
        get_local_artifact_paths(
            purl=purl,
            build_tool_purl_types=build_tool_purl_types,
            local_artifact_repo_mapper=local_artifact_repo_mapper,
        )
        == expectation
    )


@pytest.mark.parametrize(
    ("purl_str", "build_tool_purl_types", "expectation"),
    [
        pytest.param(
            "pkg:maven/com.google.guava/guava@33.2.1-jre",
            ["maven", "pypi"],
            {},
            id="A maven type PURL where multiple build tool types are discovered",
        ),
        pytest.param(
            "pkg:maven/com.google.guava/guava@33.2.1-jre",
            [],
            {},
            id="A maven type PURL where no build tool is discovered",
        ),
        pytest.param(
            "pkg:pypi/django@5.0.3",
            [],
            {},
            id="A pypi type PURL where no build tool is discovered",
        ),
    ],
)
def test_get_local_artifact_paths_not_available(
    purl_str: str,
    build_tool_purl_types: list[str],
    expectation: dict[str, list[str]],
    tmp_path: Path,
) -> None:
    """Test getting local artifact paths where the artifact paths are not available."""
    purl = PackageURL.from_string(purl_str)
    local_artifact_repo_mapper = {
        "maven": str(tmp_path),
        "pypi": str(tmp_path),
    }

    assert (
        get_local_artifact_paths(
            purl=purl,
            build_tool_purl_types=build_tool_purl_types,
            local_artifact_repo_mapper=local_artifact_repo_mapper,
        )
        == expectation
    )


def test_get_local_artifact_paths_succeeded_maven(tmp_path: Path) -> None:
    """Test getting local artifact paths succeeded with maven purl."""
    purl = PackageURL.from_string("pkg:maven/com.oracle.macaron/macaron@0.13.0")
    build_tool_purl_types = ["maven", "pypi"]

    tmp_path_str = str(tmp_path)

    local_artifact_repo_mapper = {
        "maven": f"{tmp_path_str}/.m2/repository",
        "pypi": f"{tmp_path_str}/.venv/lib/python3.11/site-packages",
    }
    maven_artifact_path = f"{local_artifact_repo_mapper['maven']}/com/oracle/macaron/macaron/0.13.0"
    os.makedirs(local_artifact_repo_mapper["maven"])
    os.makedirs(local_artifact_repo_mapper["pypi"])
    os.makedirs(maven_artifact_path)

    expectation = {
        "maven": [maven_artifact_path],
    }

    result = get_local_artifact_paths(
        purl=purl,
        build_tool_purl_types=build_tool_purl_types,
        local_artifact_repo_mapper=local_artifact_repo_mapper,
    )

    assert result == expectation


def test_get_local_artifact_paths_succeeded_pypi(tmp_path: Path) -> None:
    """Test getting local artifact paths succeeded with pypi purl."""
    purl = PackageURL.from_string("pkg:pypi/macaron@0.13.0")
    build_tool_purl_types = ["maven", "pypi"]

    tmp_path_str = str(tmp_path)

    local_artifact_repo_mapper = {
        "maven": f"{tmp_path_str}/.m2/repository",
        "pypi": f"{tmp_path_str}/.venv/lib/python3.11/site-packages",
    }
    pypi_artifact_paths = [
        f"{local_artifact_repo_mapper['pypi']}/macaron",
        f"{local_artifact_repo_mapper['pypi']}/macaron-0.13.0.dist-info",
        f"{local_artifact_repo_mapper['pypi']}/Macaron-0.13.0.dist-info",
    ]

    os.makedirs(local_artifact_repo_mapper["maven"])
    os.makedirs(local_artifact_repo_mapper["pypi"])

    for artifact_path in pypi_artifact_paths:
        os.makedirs(artifact_path)

    expectation = {
        "pypi": sorted(pypi_artifact_paths),
    }

    result = get_local_artifact_paths(
        purl=purl,
        build_tool_purl_types=build_tool_purl_types,
        local_artifact_repo_mapper=local_artifact_repo_mapper,
    )
    for value in result.values():
        value.sort()

    assert result == expectation
