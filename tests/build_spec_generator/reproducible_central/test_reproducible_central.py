# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for Reproducible Central build spec generation"""

import pytest

from macaron.build_spec_generator.macaron_db_extractor import GenericBuildCommandInfo
from macaron.build_spec_generator.reproducible_central.reproducible_central import (
    ReproducibleCentralBuildTool,
    _get_rc_build_tool_name_from_build_facts,
    get_lookup_build_command_jdk,
    get_rc_build_command,
    get_rc_default_build_command,
)
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
def test_get_rc_build_command(
    cmds_sequence: list[list[str]],
    expected: str,
) -> None:
    """Test the _get_build_command_sequence function."""
    assert get_rc_build_command(cmds_sequence) == expected


@pytest.mark.parametrize(
    ("build_tool_facts", "expected"),
    [
        pytest.param(
            [
                BuildToolFacts(
                    language="python",
                    build_tool_name="pip",
                )
            ],
            None,
            id="python_is_not_supported_for_rc",
        ),
        pytest.param(
            [
                BuildToolFacts(
                    language="java",
                    build_tool_name="gradle",
                )
            ],
            ReproducibleCentralBuildTool.GRADLE,
            id="build_tool_gradle",
        ),
        pytest.param(
            [
                BuildToolFacts(
                    language="java",
                    build_tool_name="maven",
                )
            ],
            ReproducibleCentralBuildTool.MAVEN,
            id="build_tool_maven",
        ),
        pytest.param(
            [
                BuildToolFacts(
                    language="not_java",
                    build_tool_name="maven",
                )
            ],
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
            None,
            id="test_unsupported_java_build_tool",
        ),
    ],
)
def test_get_rc_build_tool_name(
    build_tool_facts: list[BuildToolFacts],
    expected: ReproducibleCentralBuildTool | None,
) -> None:
    """Test the _get_rc_build_tool_name function."""
    assert _get_rc_build_tool_name_from_build_facts(build_tool_facts) == expected


def test_get_rc_default_build_command_unsupported() -> None:
    """Test the get_rc_default_build_command function for an unsupported RC build tool."""
    assert not get_rc_default_build_command(ReproducibleCentralBuildTool.SBT)


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
def test_get_lookup_build_command_jdk(
    build_command_info: GenericBuildCommandInfo,
    expected: str | None,
) -> None:
    """Test the get_lookup_build_command_jdk function."""
    assert get_lookup_build_command_jdk(build_command_info) == expected
