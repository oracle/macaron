# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Poetry build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.poetry import Poetry
from tests.slsa_analyzer.mock_git_utils import prepare_repo_for_testing


@pytest.mark.parametrize(
    "mock_repo",
    [
        Path(__file__).parent.joinpath("mock_repos", "poetry_repos", "has_poetry_lock"),
        Path(__file__).parent.joinpath("mock_repos", "poetry_repos", "no_poetry"),
        Path(__file__).parent.joinpath("mock_repos", "poetry_repos", "no_poetry_lock"),
    ],
)
def test_get_build_dirs(snapshot: list, poetry_tool: Poetry, mock_repo: Path) -> None:
    """Test discovering build directories."""
    assert list(poetry_tool.get_build_dirs(str(mock_repo))) == snapshot


@pytest.mark.parametrize(
    ("mock_repo", "expected_value"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "poetry_repos", "has_poetry_lock"), True),
        (Path(__file__).parent.joinpath("mock_repos", "poetry_repos", "no_poetry"), False),
        (Path(__file__).parent.joinpath("mock_repos", "poetry_repos", "no_poetry_lock"), True),
    ],
)
def test_poetry_build_tool(poetry_tool: Poetry, macaron_path: str, mock_repo: str, expected_value: bool) -> None:
    """Test the Poetry build tool."""
    base_dir = Path(__file__).parent
    ctx = prepare_repo_for_testing(mock_repo, macaron_path, base_dir)
    assert poetry_tool.is_detected(ctx.component.repository.fs_path) == expected_value
