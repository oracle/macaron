# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for build spec generation"""

import pytest
from packageurl import PackageURL

from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpecDict, SpecBuildCommandDict
from macaron.build_spec_generator.common_spec.core import (
    ECOSYSTEMS,
    LANGUAGES,
    MacaronBuildToolName,
    compose_shell_commands,
    get_language_version,
    get_macaron_build_tool_names,
)
from macaron.build_spec_generator.macaron_db_extractor import GenericBuildCommandInfo
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolFacts


@pytest.mark.parametrize(
    ("cmds_sequence", "expected"),
    [
        pytest.param(
            [
                "make clean".split(),
                "mvn clean package".split(),
            ],
            "make clean && mvn clean package",
        ),
        pytest.param(
            [
                "mvn clean package".split(),
            ],
            "mvn clean package",
        ),
    ],
)
def test_compose_shell_commands(
    cmds_sequence: list[list[str]],
    expected: str,
) -> None:
    """Test the compose_shell_commands function."""
    assert compose_shell_commands(cmds_sequence) == expected


@pytest.mark.parametrize(
    ("build_tool_facts", "language", "expected"),
    [
        pytest.param(
            [
                BuildToolFacts(
                    language="python",
                    build_tool_name="pip",
                )
            ],
            "python",
            [MacaronBuildToolName.PIP],
            id="python_pip_supported",
        ),
        pytest.param(
            [
                BuildToolFacts(
                    language="java",
                    build_tool_name="gradle",
                )
            ],
            "java",
            [MacaronBuildToolName.GRADLE],
            id="build_tool_gradle",
        ),
        pytest.param(
            [
                BuildToolFacts(
                    language="java",
                    build_tool_name="maven",
                )
            ],
            "java",
            [MacaronBuildToolName.MAVEN],
            id="build_tool_maven",
        ),
        pytest.param(
            [
                BuildToolFacts(
                    language="not_java",
                    build_tool_name="maven",
                )
            ],
            "java",
            None,
            id="java_is_the_only_supported_language",
        ),
        pytest.param(
            [
                BuildToolFacts(
                    language="java",
                    build_tool_name="some_java_build_tool",
                )
            ],
            "java",
            None,
            id="test_unsupported_java_build_tool",
        ),
    ],
)
def test_get_build_tool_name(
    build_tool_facts: list[BuildToolFacts],
    language: str,
    expected: list[MacaronBuildToolName] | None,
) -> None:
    """Test build tool name detection."""
    assert get_macaron_build_tool_names(build_tool_facts, target_language=language) == expected


@pytest.mark.parametrize(
    ("build_command_info", "expected"),
    [
        pytest.param(
            GenericBuildCommandInfo(
                command=["mvn", "package"],
                language="java",
                language_versions=["8"],
                build_tool_name="maven",
            ),
            "8",
            id="has_language_version",
        ),
        pytest.param(
            GenericBuildCommandInfo(
                command=["mvn", "package"],
                language="java",
                language_versions=[],
                build_tool_name="maven",
            ),
            None,
            id="no_language_version",
        ),
    ],
)
def test_get_language_version(
    build_command_info: GenericBuildCommandInfo,
    expected: str | None,
) -> None:
    """Test the get_language_version function."""
    assert get_language_version(build_command_info) == expected


@pytest.mark.parametrize(
    ("base_build_spec_dict"),
    [
        pytest.param(
            BaseBuildSpecDict(
                {
                    "macaron_version": "0.20.0",
                    "group_id": "foo",
                    "artifact_id": "bar",
                    "version": "1.0.0",
                    "git_repo": "bla",
                    "git_tag": "bla",
                    "newline": "lf",
                    "language_version": [],
                    "ecosystem": "maven",
                    "purl": "pkg:maven/foo/bar@1.0.0",
                    "language": LANGUAGES.MAVEN.value,
                    "build_tools": [MacaronBuildToolName.MAVEN],
                    "build_commands": [],
                }
            ),
            id="empty build command for maven",
        ),
        pytest.param(
            BaseBuildSpecDict(
                {
                    "macaron_version": "0.20.0",
                    "group_id": "foo",
                    "artifact_id": "bar",
                    "version": "1.0.0",
                    "git_repo": "bla",
                    "git_tag": "bla",
                    "newline": "lf",
                    "language_version": [],
                    "ecosystem": "maven",
                    "purl": "pkg:maven/foo/bar@1.0.0",
                    "language": LANGUAGES.MAVEN.value,
                    "build_tools": ["ant"],
                    "build_commands": [SpecBuildCommandDict(build_tool="ant", command=["ant", "dist"])],
                }
            ),
            id="unsupported build tool for maven",
        ),
        pytest.param(
            BaseBuildSpecDict(
                {
                    "macaron_version": "0.20.0",
                    "group_id": None,
                    "artifact_id": "bar",
                    "version": "1.0.0",
                    "git_repo": "bla",
                    "git_tag": "bla",
                    "newline": "lf",
                    "language_version": [],
                    "ecosystem": "pypi",
                    "purl": "pkg:pypi/bar@1.0.0",
                    "language": LANGUAGES.PYPI.value,
                    "build_tools": [MacaronBuildToolName.FLIT],
                    "build_commands": [],
                }
            ),
            id="empty build command for pypi",
        ),
        pytest.param(
            BaseBuildSpecDict(
                {
                    "macaron_version": "0.20.0",
                    "group_id": None,
                    "artifact_id": "bar",
                    "version": "1.0.0",
                    "git_repo": "bla",
                    "git_tag": "bla",
                    "newline": "lf",
                    "language_version": [],
                    "ecosystem": "pypi",
                    "purl": "pkg:pypi/bar@1.0.0",
                    "language": LANGUAGES.PYPI.value,
                    "build_tools": ["uv"],
                    "build_commands": [SpecBuildCommandDict(build_tool="uv", command=["python", "-m", "build"])],
                }
            ),
            id="unsupported build tool for pypi",
        ),
    ],
)
def test_resolve_fields(base_build_spec_dict: BaseBuildSpecDict) -> None:
    """Test the buildspec field resolution for each ecosystem."""
    ECOSYSTEMS[base_build_spec_dict["ecosystem"].upper()].value(base_build_spec_dict).resolve_fields(
        PackageURL.from_string(base_build_spec_dict["purl"])
    )
