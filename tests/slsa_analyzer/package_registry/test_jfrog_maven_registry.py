# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the ``JFrogMavenRegistry`` class."""

import os
from pathlib import Path

import pytest

from macaron.config.defaults import load_defaults
from macaron.errors import ConfigurationError
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.build_tool.pip import Pip
from macaron.slsa_analyzer.build_tool.poetry import Poetry
from macaron.slsa_analyzer.package_registry.jfrog_maven_registry import JFrogMavenAssetMetadata, JFrogMavenRegistry


@pytest.fixture(name="jfrog_maven")
def jfrog_maven_instance() -> JFrogMavenRegistry:
    """Provide a default ``JFrogMavenRegistry`` object used in the tests below."""
    return JFrogMavenRegistry(
        domain="registry.jfrog.com",
        repo="repo",
        enabled=True,
    )


def test_load_defaults(tmp_path: Path) -> None:
    """Test the ``load_defaults`` method."""
    user_config_path = os.path.join(tmp_path, "config.ini")
    user_config_input = """
        [package_registry.jfrog.maven]
        domain = jfrog.registry.xyz
        repo = prod-repo
        request_timeout = 5
        download_timeout = 300
    """
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)

    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)

    jfrog_maven = JFrogMavenRegistry()
    jfrog_maven.load_defaults()
    assert jfrog_maven.domain == "jfrog.registry.xyz"
    assert jfrog_maven.repo == "prod-repo"
    assert jfrog_maven.request_timeout == 5
    assert jfrog_maven.download_timeout == 300


def test_load_defaults_without_jfrog_maven_config() -> None:
    """Test the ``load_defaults`` method in trivial case when no config is given."""
    jfrog_maven = JFrogMavenRegistry()
    jfrog_maven.load_defaults()


@pytest.mark.parametrize(
    ("user_config_input"),
    [
        pytest.param(
            """
            [package_registry.jfrog.maven]
            repo = prod-repo
            """,
            id="Missing domain",
        ),
        pytest.param(
            """
            [package_registry.jfrog.maven]
            domain = jfrog.registry.xyz
            """,
            id="Missing repo",
        ),
        pytest.param(
            """
            [package_registry.jfrog.maven]
            domain = jfrog.registry.xyz
            repo = prod-repo
            request_timeout = foo
            """,
            id="Invalid value for request_timeout",
        ),
        pytest.param(
            """
            [package_registry.jfrog.maven]
            domain = jfrog.registry.xyz
            repo = prod-repo
            download_timeout = foo
            """,
            id="Invalid value for download_timeout",
        ),
    ],
)
def test_load_defaults_with_invalid_config(tmp_path: Path, user_config_input: str) -> None:
    """Test the ``load_defaults`` method in case the config is invalid."""
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)

    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)

    jfrog_maven = JFrogMavenRegistry()
    with pytest.raises(ConfigurationError):
        jfrog_maven.load_defaults()


@pytest.mark.parametrize(
    ("build_tool", "expected_result"),
    [
        (Maven(), True),
        (Gradle(), True),
        (Pip(), False),
        (Poetry(), False),
    ],
)
def test_is_detected(
    jfrog_maven: JFrogMavenRegistry,
    build_tool: BaseBuildTool,
    expected_result: bool,
) -> None:
    """Test the ``is_detected`` method."""
    assert jfrog_maven.is_detected(build_tool) == expected_result

    # The method always returns False when the jfrog_maven instance is not enabled
    # (in the ini config).
    jfrog_maven.enabled = False
    assert jfrog_maven.is_detected(build_tool) is False


@pytest.mark.parametrize(
    ("args", "expected_path"),
    [
        pytest.param(
            {
                "group_id": "io.micronaut",
            },
            "io/micronaut",
            id="Only group_id 1",
        ),
        pytest.param(
            {
                "group_id": "com.fasterxml.jackson.core",
            },
            "com/fasterxml/jackson/core",
            id="Only group_id 2",
        ),
        pytest.param(
            {
                "group_id": "com.fasterxml.jackson.core",
                "artifact_id": "jackson-annotations",
            },
            "com/fasterxml/jackson/core/jackson-annotations",
            id="group_id and artifact_id",
        ),
        pytest.param(
            {
                "group_id": "com.fasterxml.jackson.core",
                "artifact_id": "jackson-annotations",
                "version": "2.9.9",
            },
            "com/fasterxml/jackson/core/jackson-annotations/2.9.9",
            id="group_id and artifact_id and version",
        ),
        pytest.param(
            {
                "group_id": "com.fasterxml.jackson.core",
                "artifact_id": "jackson-annotations",
                "version": "2.9.9",
                "asset_name": "jackson-annotations-2.9.9.jar",
            },
            "com/fasterxml/jackson/core/jackson-annotations/2.9.9/jackson-annotations-2.9.9.jar",
            id="group_id and artifact_id and version and asset_name,",
        ),
    ],
)
def test_construct_maven_path(
    jfrog_maven: JFrogMavenRegistry,
    args: dict,
    expected_path: str,
) -> None:
    """Test the ``construct_maven_path`` method."""
    assert jfrog_maven.construct_maven_path(**args) == expected_path


@pytest.mark.parametrize(
    ("group_id", "expected_group_path"),
    [
        (
            "io.micronaut",
            "io/micronaut",
        ),
        (
            "com.fasterxml.jackson.core",
            "com/fasterxml/jackson/core",
        ),
    ],
)
def test_to_group_folder_path(
    jfrog_maven: JFrogMavenRegistry,
    group_id: str,
    expected_group_path: str,
) -> None:
    """Test the ``to_gorup_folder_path`` method."""
    assert jfrog_maven.construct_maven_path(group_id) == expected_group_path


@pytest.mark.parametrize(
    ("folder_path", "expected_url"),
    [
        (
            "io/micronaut/micronaut-jdbc",
            "https://registry.jfrog.com/api/storage/repo/io/micronaut/micronaut-jdbc",
        ),
        (
            "com/fasterxml/jackson/core/jackson-annotations",
            "https://registry.jfrog.com/api/storage/repo/com/fasterxml/jackson/core/jackson-annotations",
        ),
    ],
)
def test_construct_folder_info_url(
    jfrog_maven: JFrogMavenRegistry,
    folder_path: str,
    expected_url: str,
) -> None:
    """Test the ``construct_folder_info_url`` method."""
    assert jfrog_maven.construct_folder_info_url(folder_path) == expected_url


@pytest.mark.parametrize(
    ("file_path", "expected_url"),
    [
        (
            "com/fasterxml/jackson/core/jackson-annotations/2.9.9/jackson-annotations-2.9.9.jar",
            (
                "https://registry.jfrog.com/api/storage/repo/"
                "com/fasterxml/jackson/core/jackson-annotations/2.9.9/jackson-annotations-2.9.9.jar"
            ),
        ),
        (
            "com/fasterxml/jackson/core/jackson-annotations",
            "https://registry.jfrog.com/api/storage/repo/com/fasterxml/jackson/core/jackson-annotations",
        ),
    ],
)
def test_construct_file_info_url(
    jfrog_maven: JFrogMavenRegistry,
    file_path: str,
    expected_url: str,
) -> None:
    """Test the ``construct_file_info_url`` method."""
    assert jfrog_maven.construct_file_info_url(file_path) == expected_url


@pytest.mark.parametrize(
    ("args", "expected_url"),
    [
        pytest.param(
            {
                "group_id": "io.micronaut",
                "artifact_id": "micronaut-jdbc",
            },
            "https://registry.jfrog.com/api/search/latestVersion?repos=repo&g=io.micronaut&a=micronaut-jdbc",
        ),
        pytest.param(
            {
                "group_id": "com.fasterxml.jackson.core",
                "artifact_id": "jackson-annotations",
            },
            "https://registry.jfrog.com/api/search/latestVersion?repos=repo&g=com.fasterxml.jackson.core&a=jackson-annotations",  # noqa: B950
        ),
    ],
)
def test_construct_latest_version_url(
    jfrog_maven: JFrogMavenRegistry,
    args: dict,
    expected_url: str,
) -> None:
    """Test the ``construct_latest_version_url`` method."""
    assert jfrog_maven.construct_latest_version_url(**args) == expected_url


@pytest.mark.parametrize(
    ("folder_info_payload", "expected_folder_names"),
    [
        pytest.param(
            """
            {
                "children": [
                    {
                        "uri": "/child1",
                        "folder": true
                    },
                    {
                        "uri": "/child2",
                        "folder": false
                    }
                ]
            }
            """,
            ["child1"],
            id="Payload with both files and folders",
        ),
        pytest.param(
            """
            {
                "children": [
                    {
                        "uri": "/jackson-annotations",
                        "folder": true
                    },
                    {
                        "uri": "/jackson-core",
                        "folder": true
                    }
                ]
            }
            """,
            ["jackson-annotations", "jackson-core"],
            id="Payload with folders only",
        ),
    ],
)
def test_extract_folder_names_from_folder_info_payload(
    jfrog_maven: JFrogMavenRegistry,
    folder_info_payload: str,
    expected_folder_names: list[str],
) -> None:
    """Test the ``extract_folder_names_from_folder_info_payload`` method."""
    assert jfrog_maven.extract_folder_names_from_folder_info_payload(folder_info_payload) == expected_folder_names


@pytest.mark.parametrize(
    ("args", "expected_file_names"),
    [
        pytest.param(
            {
                "folder_info_payload": """
                    {
                        "children": [
                            {
                                "uri": "/child1",
                                "folder": true
                            },
                            {
                                "uri": "/child2",
                                "folder": false
                            }
                        ]
                    }
                """
            },
            ["child2"],
            id="Payload with both files and folders",
        ),
        pytest.param(
            {
                "folder_info_payload": """
                    {
                        "children": [
                            {
                                "uri": "/jackson-databind-2.9.9.jar",
                                "folder": false
                            },
                            {
                                "uri": "/jackson-databind-2.9.9.jar.asc",
                                "folder": false
                            },
                            {
                                "uri": "/jackson-databind-2.9.9.jar.md5",
                                "folder": false
                            },
                            {
                                "uri": "/jackson-databind-2.9.9.jar.sha1",
                                "folder": false
                            },
                            {
                                "uri": "/multiple.intoto.jsonl",
                                "folder": false
                            }
                        ]
                    }
                """,
                "extensions": ["jar"],
            },
            ["jackson-databind-2.9.9.jar"],
            id="One allowed extension 1",
        ),
        pytest.param(
            {
                "folder_info_payload": """
                    {
                        "children": [
                            {
                                "uri": "/jackson-databind-2.9.9.jar",
                                "folder": false
                            },
                            {
                                "uri": "/jackson-databind-2.9.9.jar.md5",
                                "folder": false
                            },
                            {
                                "uri": "/jackson-databind-2.9.9-javadoc.jar",
                                "folder": false
                            },
                            {
                                "uri": "/jackson-databind-2.9.9-javadoc.jar.md5",
                                "folder": false
                            },
                            {
                                "uri": "/jackson-databind-2.9.9-sources.jar",
                                "folder": false
                            },
                            {
                                "uri": "/jackson-databind-2.9.9-sources.jar.md5",
                                "folder": false
                            },
                            {
                                "uri": "/multiple.intoto.jsonl",
                                "folder": false
                            }
                        ]
                    }
                """,
                "extensions": ["jar"],
            },
            [
                "jackson-databind-2.9.9.jar",
                "jackson-databind-2.9.9-javadoc.jar",
                "jackson-databind-2.9.9-sources.jar",
            ],
            id="One allowed extension 2",
        ),
        pytest.param(
            {
                "folder_info_payload": """
                    {
                        "children": [
                            {
                                "uri": "/jackson-databind-2.9.9.jar",
                                "folder": false
                            },
                            {
                                "uri": "/jackson-databind-2.9.9.jar.asc",
                                "folder": false
                            },
                            {
                                "uri": "/jackson-databind-2.9.9.jar.md5",
                                "folder": false
                            },
                            {
                                "uri": "/jackson-databind-2.9.9.jar.sha1",
                                "folder": false
                            },
                            {
                                "uri": "/multiple.intoto.jsonl",
                                "folder": false
                            }
                        ]
                    }
                """,
                "extensions": ["jar", "intoto.jsonl"],
            },
            ["jackson-databind-2.9.9.jar", "multiple.intoto.jsonl"],
            id="Multiple allowed extensions",
        ),
        pytest.param({"folder_info_payload": "{}"}, [], id="Malformed payload 1"),
        pytest.param(
            {
                "folder_info_payload": """
                    {
                        "children": {}
                    }
                """,
            },
            [],
            id="Malformed payload 2",
        ),
        pytest.param(
            {
                "folder_info_payload": """
                    {
                        "children": [
                            {
                                "uri": "/jackson-databind-2.9.9.jar",
                                "folder": false
                            },
                            {
                                "uri": {},
                                "folder": false
                            },
                            {
                                "uri": "/foo"
                            },
                            {
                                "uri": "/multiple.intoto.jsonl",
                                "folder": false
                            }
                        ]
                    }
                """,
            },
            ["jackson-databind-2.9.9.jar", "multiple.intoto.jsonl"],
            id="Malformed payload 3",
        ),
    ],
)
def test_extract_file_names_from_folder_info_payload(
    jfrog_maven: JFrogMavenRegistry,
    args: dict,
    expected_file_names: list[str],
) -> None:
    """Test the ``extract_file_names_from_folder_info_payload`` method."""
    assert jfrog_maven.extract_file_names_from_folder_info_payload(**args) == expected_file_names


@pytest.mark.parametrize(
    ("file_info_payload", "expected_metadata"),
    [
        pytest.param(
            """
            {
                "size": "66897",
                "checksums": {
                    "sha1": "d735e01f9d6e3f31166a6783903a400faaf30376",
                    "md5": "bcdc3d1df2197c73fcc95189372a1247",
                    "sha256": "17918b3097285da88371fac925922902a9fe60f075237e76f406c09234c8d614"
                },
                "downloadUri": "https://registry.jfrog.com/repo/com/fasterxml/jackson/core/jackson-annotations/2.9.9/jackson-annotations-2.9.9.jar"
            }
            """,  # noqa: B950
            JFrogMavenAssetMetadata(
                size_in_bytes=66897,
                sha256_digest="17918b3097285da88371fac925922902a9fe60f075237e76f406c09234c8d614",
                download_uri="https://registry.jfrog.com/repo/com/fasterxml/jackson/core/jackson-annotations/2.9.9/jackson-annotations-2.9.9.jar",  # noqa: B950
            ),
            id="Valid",
        ),
    ],
)
def test_extract_asset_metadata_from_file_info_payload(
    jfrog_maven: JFrogMavenRegistry,
    file_info_payload: str,
    expected_metadata: JFrogMavenAssetMetadata,
) -> None:
    """Test the ``extract_asset_metadata_from_file_info_payload`` method."""
    assert jfrog_maven.extract_asset_metadata_from_file_info_payload(file_info_payload) == expected_metadata
