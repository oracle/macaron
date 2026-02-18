# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains tests for Reproducible Central build spec generation."""

import pytest

from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpecDict, SpecBuildCommandDict
from macaron.build_spec_generator.common_spec.core import compose_shell_commands
from macaron.build_spec_generator.reproducible_central.reproducible_central import gen_reproducible_central_build_spec
from macaron.errors import GenerateBuildSpecError


@pytest.fixture(name="base_build_spec")
def fixture_base_build_spec() -> BaseBuildSpecDict:
    """Create a base build spec object."""
    return BaseBuildSpecDict(
        {
            "macaron_version": "1.0.0",
            "ecosystem": "maven",
            "language": "java",
            "group_id": "com.oracle",
            "artifact_id": "example-artifact",
            "version": "1.2.3",
            "git_repo": "https://github.com/oracle/example-artifact.git",
            "git_tag": "sampletag",
            "build_tools": ["maven"],
            "newline": "lf",
            "language_version": ["17"],
            "build_commands": [SpecBuildCommandDict(build_tool="maven", command=["mvn", "package"])],
            "purl": "pkg:maven/com.oracle/example-artifact@1.2.3",
        }
    )


def test_successful_build_spec(base_build_spec: BaseBuildSpecDict) -> None:
    """Check the build spec content."""
    content = gen_reproducible_central_build_spec(base_build_spec)
    assert isinstance(content, str), "Expected this build spec to be a string."
    assert "groupId=com.oracle" in content
    assert "artifactId=example-artifact" in content
    assert "tool=mvn" in content
    assert 'command="mvn package"' in content


def test_unsupported_build_tool(base_build_spec: BaseBuildSpecDict) -> None:
    """Test an unsupported build tool name."""
    base_build_spec["build_tools"] = ["unsupported_tool"]
    with pytest.raises(GenerateBuildSpecError) as excinfo:
        gen_reproducible_central_build_spec(base_build_spec)
    assert "is not supported by Reproducible Central" in str(excinfo.value)


def test_missing_group_id(base_build_spec: BaseBuildSpecDict) -> None:
    """Test when group ID is None."""
    base_build_spec["group_id"] = None
    with pytest.raises(GenerateBuildSpecError) as excinfo:
        gen_reproducible_central_build_spec(base_build_spec)
    assert "Version is missing in PURL" in str(excinfo.value)


@pytest.mark.parametrize(
    ("build_tools", "expected"),
    [
        (["maven", "pip"], "mvn"),
        (["gradle"], "gradle"),
        (["MAVEN"], "mvn"),
        (["GRADLE", "pip"], "gradle"),
    ],
)
def test_build_tool_name_variants(base_build_spec: BaseBuildSpecDict, build_tools: list[str], expected: str) -> None:
    """Test the correct handling of build tool names."""
    base_build_spec["build_tools"] = build_tools
    content = gen_reproducible_central_build_spec(base_build_spec)
    assert content
    assert f"tool={expected}" in content


def test_compose_shell_commands_integration(base_build_spec: BaseBuildSpecDict) -> None:
    """Test that the correct compose_shell_commands function is used."""
    base_build_spec["build_commands"] = [
        SpecBuildCommandDict(build_tool="maven", command=["mvn", "clean", "package"]),
        SpecBuildCommandDict(build_tool="maven", command=["mvn", "deploy"]),
    ]
    content = gen_reproducible_central_build_spec(base_build_spec)
    expected_commands = compose_shell_commands([["mvn", "clean", "package"], ["mvn", "deploy"]])
    assert content
    assert f'command="{expected_commands}"' in content
