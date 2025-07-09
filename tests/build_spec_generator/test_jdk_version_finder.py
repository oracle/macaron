# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the jdk_finder module."""

import zipfile
from pathlib import Path

import pytest

from macaron.build_spec_generator.jdk_finder import get_jdk_version_from_jar, join_remote_maven_repo_url


@pytest.mark.parametrize(
    ("remote_maven_url", "maven_repo_path", "expected"),
    [
        pytest.param(
            "https://repo1.maven.org/maven2",
            "com/oracle/",
            "https://repo1.maven.org/maven2/com/oracle/",
            id="g_coordinate",
        ),
        pytest.param(
            "https://repo1.maven.org/maven2",
            "com/oracle/macaron/",
            "https://repo1.maven.org/maven2/com/oracle/macaron/",
            id="ga_coordinate",
        ),
        pytest.param(
            "https://repo1.maven.org/maven2",
            "com/oracle/macaron/0.16.0/",
            "https://repo1.maven.org/maven2/com/oracle/macaron/0.16.0/",
            id="gav_coordinate",
        ),
        pytest.param(
            "https://repo1.maven.org/maven2",
            "com/oracle/macaron/0.16.0/macaron-0.16.0.jar",
            "https://repo1.maven.org/maven2/com/oracle/macaron/0.16.0/macaron-0.16.0.jar",
            id="gav_asset_coordinate",
        ),
        pytest.param(
            "https://repo1.maven.org/maven2/",
            "com/oracle/macaron/0.16.0/",
            "https://repo1.maven.org/maven2/com/oracle/macaron/0.16.0/",
            id="handle_trailing_slash_in_remote_maven_url",
        ),
    ],
)
def test_join_remote_maven_repo_url(
    remote_maven_url: str,
    maven_repo_path: str,
    expected: str,
) -> None:
    """Test the join remote maven repo url function."""
    assert (
        join_remote_maven_repo_url(
            remote_maven_url=remote_maven_url,
            maven_repo_path=maven_repo_path,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("manifest_mf_content", "expected"),
    [
        ("Build-Jdk: 1.8", "1.8"),
        ("Build-Jdk-Spec: 8", "8"),
    ],
)
def test_get_jdk_version_from_jar_succeed(
    tmp_path: Path,
    manifest_mf_content: str,
    expected: str,
) -> None:
    """Test the get_jdk_version_from_jar function on valid cases."""
    test_jar_file = tmp_path / "example.jar"

    with zipfile.ZipFile(test_jar_file, mode="w") as test_jar:
        test_jar.writestr("META-INF/MANIFEST.MF", manifest_mf_content)

    assert get_jdk_version_from_jar(str(test_jar_file)) == expected


@pytest.mark.parametrize(
    ("manifest_mf_content"),
    [
        (""),
        ("Build-Jdk-Spec: "),
    ],
)
def test_get_jdk_version_from_jar_failed(
    tmp_path: Path,
    manifest_mf_content: str,
) -> None:
    """Test the get_jdk_version_from_jar function on error cases."""
    test_jar_file = tmp_path / "example.jar"

    with zipfile.ZipFile(test_jar_file, mode="w") as test_jar:
        test_jar.writestr("META-INF/MANIFEST.MF", manifest_mf_content)

    assert not get_jdk_version_from_jar(str(test_jar_file))
