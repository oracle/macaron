# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the NPM build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.npm import NPM
from tests.slsa_analyzer.mock_git_utils import prepare_repo_for_testing


@pytest.mark.parametrize(
    "mock_repo",
    [
        Path(__file__).parent.joinpath("mock_repos", "npm_repos", "root_package"),
        Path(__file__).parent.joinpath("mock_repos", "npm_repos", "root_package_packagelock"),
        Path(__file__).parent.joinpath("mock_repos", "npm_repos", "nested_package"),
        Path(__file__).parent.joinpath("mock_repos", "npm_repos", "no_package"),
    ],
)
def test_get_build_dirs(snapshot: list, npm_tool: NPM, mock_repo: Path) -> None:
    """Test discovering build directories."""
    assert list(npm_tool.get_build_dirs(str(mock_repo))) == snapshot


@pytest.mark.parametrize(
    ("mock_repo", "expected_value"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "npm_repos", "root_package"), True),
        (Path(__file__).parent.joinpath("mock_repos", "npm_repos", "root_package_packagelock"), True),
        (Path(__file__).parent.joinpath("mock_repos", "npm_repos", "nested_package"), True),
        (Path(__file__).parent.joinpath("mock_repos", "npm_repos", "no_package"), False),
    ],
)
def test_npm_build_tool(npm_tool: NPM, macaron_path: str, mock_repo: str, expected_value: bool) -> None:
    """Test the Maven build tool."""
    base_dir = Path(__file__).parent
    ctx = prepare_repo_for_testing(mock_repo, macaron_path, base_dir)
    assert npm_tool.is_detected(ctx.component.repository.fs_path) == expected_value
