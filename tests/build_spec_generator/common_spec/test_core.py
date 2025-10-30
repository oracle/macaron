# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for build spec generation"""

import pytest

from macaron.build_spec_generator.common_spec.core import (
    MacaronBuildToolName,
    compose_shell_commands,
    get_language_version,
    get_macaron_build_tool_name,
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
            MacaronBuildToolName.PIP,
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
            MacaronBuildToolName.GRADLE,
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
            MacaronBuildToolName.MAVEN,
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
    expected: MacaronBuildToolName | None,
) -> None:
    """Test build tool name detection."""
    assert get_macaron_build_tool_name(build_tool_facts, target_language=language) == expected


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
