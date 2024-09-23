# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Test the local artifact utilities."""

import tempfile
from collections.abc import Mapping

import pytest
from packageurl import PackageURL

from macaron.artifact.local_artifact import construct_local_artifact_paths_from_purl, get_local_artifact_paths


@pytest.mark.parametrize(
    ("build_purl_type", "purl_str", "local_artifact_repo_mapper", "expectation"),
    [
        pytest.param(
            "maven",
            "pkg:maven/com.google.guava/guava@33.2.1-jre",
            {"maven": "/home/foo/.m2"},
            ["/home/foo/.m2/repository/com/google/guava/guava/33.2.1-jre"],
            id="A maven type PURL with available local maven repo",
        ),
        pytest.param(
            "maven",
            "pkg:maven/com.google.guava/guava@33.2.1-jre",
            {},
            None,
            id="A maven type PURL without an available local maven repo",
        ),
        pytest.param(
            "maven",
            "pkg:maven/com.google.guava/guava@33.2.1-jre",
            {"pypi": "/home/foo/.venv"},
            None,
            id="A maven type PURL without an available local maven repo but there is a Python venv",
        ),
        pytest.param(
            "maven",
            "pkg:maven/com.google.guava/guava",
            {"maven": "/home/foo/.m2"},
            None,
            id="A maven type PURL with missing version and an available local maven repo",
        ),
        pytest.param(
            "maven",
            "pkg:maven/guava",
            {"maven": "/home/foo/.m2"},
            None,
            id="A maven type PURL with missing groupd Id and an available local maven repo",
        ),
        pytest.param(
            "maven",
            "pkg:github/oracle/macaron",
            {"maven": "/home/foo/.m2"},
            None,
            id="A git type PURL and an available local maven repo",
        ),
    ],
)
def test_construct_local_artifact_path_from_purl(
    build_purl_type: str,
    purl_str: str,
    local_artifact_repo_mapper: Mapping[str, str],
    expectation: list[str],
) -> None:
    """Test constructing a local artifact path from a given purl."""
    component_purl = PackageURL.from_string(purl_str)
    assert (
        construct_local_artifact_paths_from_purl(
            build_purl_type=build_purl_type,
            component_purl=component_purl,
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
            {"maven": []},
            id="A maven type PURL where multiple build tool types are discovered. But no artifact path is available.",
        ),
    ],
)
def test_get_local_artifact_paths_non_existing(
    purl_str: str,
    build_tool_purl_types: list[str],
    expectation: dict[str, list[str]],
) -> None:
    """Test getting local artifact paths of non existing artifacts.

    The local artifact repos are available.
    """
    purl = PackageURL.from_string(purl_str)
    with tempfile.TemporaryDirectory() as temp_dir:
        local_artifact_repo_mapper = {
            "maven": temp_dir,
            "pypi": temp_dir,
        }
        assert (
            get_local_artifact_paths(
                purl=purl,
                build_tool_purl_types=build_tool_purl_types,
                local_artifact_repo_mapper=local_artifact_repo_mapper,
            )
            == expectation
        )
