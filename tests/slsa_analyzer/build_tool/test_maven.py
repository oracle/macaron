# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Maven build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.maven import Maven
from tests.slsa_analyzer.mock_git_utils import prepare_repo_for_testing


@pytest.mark.parametrize(
    "mock_repo",
    [
        Path(__file__).parent.joinpath("mock_repos", "maven_repos", "has_parent_pom"),
        Path(__file__).parent.joinpath("mock_repos", "maven_repos", "no_parent_pom"),
        Path(__file__).parent.joinpath("mock_repos", "maven_repos", "no_pom"),
    ],
)
def test_get_build_dirs(snapshot: list, maven_tool: Maven, mock_repo: Path) -> None:
    """Test discovering build directories."""
    assert list(maven_tool.get_build_dirs(str(mock_repo))) == snapshot


@pytest.mark.parametrize(
    ("mock_repo", "expected_value"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "maven_repos", "has_parent_pom"), True),
        (Path(__file__).parent.joinpath("mock_repos", "maven_repos", "no_parent_pom"), True),
        (Path(__file__).parent.joinpath("mock_repos", "maven_repos", "no_pom"), False),
    ],
)
def test_maven_build_tool(maven_tool: Maven, macaron_path: str, mock_repo: str, expected_value: bool) -> None:
    """Test the Maven build tool."""
    base_dir = Path(__file__).parent
    ctx = prepare_repo_for_testing(mock_repo, macaron_path, base_dir)
    assert maven_tool.is_detected(ctx.component.repository.fs_path) == expected_value
