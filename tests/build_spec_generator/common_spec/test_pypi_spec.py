# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for PyPI build spec defaults."""

import pytest

from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpecDict, SpecBuildCommandDict
from macaron.build_spec_generator.common_spec.pypi_spec import PyPIBuildSpec


@pytest.mark.parametrize(
    ("build_tool", "expected_command"),
    [
        ("poetry", ["poetry", "build"]),
        ("flit", ["flit", "build"]),
        ("uv", ["uv", "build"]),
    ],
)
def test_set_default_build_commands_for_pypi_tools(build_tool: str, expected_command: list[str]) -> None:
    """Ensure known PyPI build tools map to expected default build commands."""
    spec = PyPIBuildSpec(
        BaseBuildSpecDict(
            {
                "ecosystem": "pypi",
                "purl": "pkg:pypi/example@1.0.0",
                "language": "python",
                "build_tools": [build_tool],
                "macaron_version": "test",
                "artifact_id": "example",
                "version": "1.0.0",
                "language_version": [],
                "build_commands": [],
            }
        )
    )
    build_cmd_spec = SpecBuildCommandDict(
        build_tool=build_tool,
        command=[],
        build_config_path="pyproject.toml",
        confidence_score=1.0,
    )

    spec.set_default_build_commands(build_cmd_spec)
    assert build_cmd_spec["command"] == expected_command
