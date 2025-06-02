# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Test the local artifact utilities."""

import os
import tempfile
from pathlib import Path

import pytest
from packageurl import PackageURL

from macaron.artifact.local_artifact import (
    construct_local_artifact_dirs_glob_pattern_maven_purl,
    construct_local_artifact_dirs_glob_pattern_pypi_purl,
    find_artifact_dirs_from_python_venv,
    get_local_artifact_dirs,
    get_local_artifact_hash,
)
from macaron.artifact.maven import construct_primary_jar_file_name
from macaron.errors import LocalArtifactFinderError


def is_case_sensitive_filesystem() -> bool:
    """Check if the filesystem is case-sensitive."""
    with tempfile.TemporaryDirectory() as temp_dir:
        lower = os.path.join(temp_dir, "a")
        upper = os.path.join(temp_dir, "A")

        os.mkdir(lower)

        try:
            os.mkdir(upper)
            # if upper is not treated the same as lower -> case sensitive
            return True
        except FileExistsError:
            # upper is treated the same as lower -> case insensitive
            return False


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
    result = construct_local_artifact_dirs_glob_pattern_maven_purl(maven_purl=maven_purl)
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
    result = construct_local_artifact_dirs_glob_pattern_maven_purl(maven_purl=maven_purl)
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
    result = construct_local_artifact_dirs_glob_pattern_pypi_purl(pypi_purl=pypi_purl)
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
    result = construct_local_artifact_dirs_glob_pattern_pypi_purl(pypi_purl=pypi_purl)
    assert result is None


def test_find_artifact_paths_from_invalid_python_venv() -> None:
    """Test find_artifact_paths_from_python_venv method with invalid venv path"""
    with pytest.raises(LocalArtifactFinderError):
        find_artifact_dirs_from_python_venv("./does-not-exist", ["django", "django-5.0.6.dist-info"])


@pytest.mark.parametrize(
    ("purl_str", "expectation"),
    [
        pytest.param(
            "pkg:maven/com.google.guava/guava@33.2.1-jre",
            [],
            id="A maven type PURL",
        ),
        pytest.param(
            "pkg:pypi/django@5.0.3",
            [],
            id="A pypi type PURL",
        ),
    ],
)
def test_get_local_artifact_paths_not_available(
    purl_str: str,
    expectation: list[str],
    tmp_path: Path,
) -> None:
    """Test getting local artifact paths where we cannot find local artifacts for the PURL."""
    purl = PackageURL.from_string(purl_str)

    assert (
        get_local_artifact_dirs(
            purl=purl,
            local_artifact_repo_path=str(tmp_path),
        )
        == expectation
    )


@pytest.mark.parametrize(
    ("purl_str"),
    [
        pytest.param(
            "pkg:maven/com.google.guava/guava",
            id="A maven type PURL with no version",
        ),
        pytest.param(
            "pkg:maven/guava@33.2.1-jre",
            id="A maven type PURL with no group",
        ),
        pytest.param(
            "pkg:maven/guava",
            id="A maven type PURL with no group and no version",
        ),
        pytest.param(
            "pkg:pypi/django",
            id="A pypi type PURL without version",
        ),
        pytest.param(
            "pkg:github/oracle/macaron",
            id="A github type PURL (unsupported)",
        ),
    ],
)
def test_get_local_artifact_paths_invalid_purl(
    purl_str: str,
    tmp_path: Path,
) -> None:
    """Test getting local artifact paths where the input PURL is invalid."""
    purl = PackageURL.from_string(purl_str)

    with pytest.raises(LocalArtifactFinderError):
        get_local_artifact_dirs(
            purl=purl,
            local_artifact_repo_path=str(tmp_path),
        )


def test_get_local_artifact_paths_succeeded_maven(tmp_path: Path) -> None:
    """Test getting local artifact paths succeeded with maven purl."""
    purl = PackageURL.from_string("pkg:maven/com.oracle.macaron/macaron@0.13.0")

    tmp_path_str = str(tmp_path)

    maven_local_repo_path = f"{tmp_path_str}/.m2/repository"
    target_artifact_path = f"{maven_local_repo_path}/com/oracle/macaron/macaron/0.13.0"
    os.makedirs(maven_local_repo_path)
    os.makedirs(target_artifact_path)

    result = get_local_artifact_dirs(
        purl=purl,
        local_artifact_repo_path=maven_local_repo_path,
    )

    assert result == [target_artifact_path]


def test_get_local_artifact_paths_succeeded_pypi(tmp_path: Path) -> None:
    """Test getting local artifact paths succeeded with pypi purl."""
    purl = PackageURL.from_string("pkg:pypi/macaron@0.13.0")

    tmp_path_str = str(tmp_path)

    python_venv_path = f"{tmp_path_str}/.venv/lib/python3.11/site-packages"

    # We are also testing if the patterns match case-insensitively.
    if not is_case_sensitive_filesystem():
        pypi_artifact_paths = [
            f"{python_venv_path}/macaron",
            f"{python_venv_path}/macaron-0.13.0.dist-info",
            f"{python_venv_path}/macaron-0.13.0.data",
        ]
    else:
        pypi_artifact_paths = [
            f"{python_venv_path}/macaron",
            f"{python_venv_path}/macaron-0.13.0.dist-info",
            f"{python_venv_path}/Macaron-0.13.0.dist-info",
            f"{python_venv_path}/macaron-0.13.0.data",
            f"{python_venv_path}/Macaron-0.13.0.data",
        ]

    os.makedirs(python_venv_path)

    for artifact_path in pypi_artifact_paths:
        os.makedirs(artifact_path)

    result = get_local_artifact_dirs(
        purl=purl,
        local_artifact_repo_path=python_venv_path,
    )

    assert sorted(result) == sorted(pypi_artifact_paths)


def test_get_local_artifact_hash() -> None:
    """Test the get local artifact hash function."""
    artifact_purl = PackageURL.from_string("pkg:maven/test/test@1")
    artifact_jar_name = construct_primary_jar_file_name(artifact_purl)

    assert artifact_jar_name

    with tempfile.TemporaryDirectory() as temp_dir:
        artifact_path = os.path.join(temp_dir, artifact_jar_name)
        with open(artifact_path, "w", encoding="utf8") as file:
            file.write("1")

        # A file containing: "1".
        target_hash = "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"

        assert target_hash == get_local_artifact_hash(artifact_purl, [temp_dir])
