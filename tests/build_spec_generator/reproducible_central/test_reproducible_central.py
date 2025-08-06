# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for Reproducible Central build spec generation"""

import pytest

from macaron.build_spec_generator.reproducible_central.reproducible_central import (
    _get_build_command_sequence,
    _get_extra_comments,
    _get_rc_build_tool_name,
    _ReproducibleCentralBuildToolName,
)
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolFacts


@pytest.mark.parametrize(
    ("comments", "expected"),
    [
        pytest.param(
            [
                "Input PURL - pkg:maven/oracle/macaron@v0.16.0",
                "Initial default JDK version 8 and default build command boo",
            ],
            "# Input PURL - pkg:maven/oracle/macaron@v0.16.0\n# Initial default JDK version 8 and default build command boo",
        ),
        pytest.param(
            [
                "Input PURL - pkg:maven/oracle/macaron@v0.16.0",
            ],
            "# Input PURL - pkg:maven/oracle/macaron@v0.16.0",
        ),
        pytest.param(
            [],
            "",
        ),
    ],
)
def test_get_extra_comments(comments: list[str], expected: str) -> None:
    """Test the _get_extra_comments function."""
    assert _get_extra_comments(comments) == expected


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
def test_get_build_command_sequence(
    cmds_sequence: list[list[str]],
    expected: str,
) -> None:
    """Test the _get_build_command_sequence function."""
    assert _get_build_command_sequence(cmds_sequence) == expected


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
            _ReproducibleCentralBuildToolName.GRADLE,
            id="build_tool_gradle",
        ),
        pytest.param(
            [
                BuildToolFacts(
                    language="java",
                    build_tool_name="maven",
                )
            ],
            _ReproducibleCentralBuildToolName.MAVEN,
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
    expected: _ReproducibleCentralBuildToolName | None,
) -> None:
    """Test the _get_rc_build_tool_name function."""
    assert _get_rc_build_tool_name(build_tool_facts) == expected
