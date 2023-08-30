# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Go build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.go import Go
from tests.slsa_analyzer.mock_git_utils import prepare_repo_for_testing


@pytest.mark.parametrize(
    "mock_repo",
    [
        Path(__file__).parent.joinpath("mock_repos", "go_repos", "no_go_mod"),
        # TODO: Having an extra go.mod breaks the pre-commit hooks; investigate a fix
        # Path(__file__).parent.joinpath("mock_repos", "go_repos", "go_mod"),
    ],
)
def test_get_build_dirs(snapshot: list, go_tool: Go, mock_repo: Path) -> None:
    """Test discovering build directories."""
    assert list(go_tool.get_build_dirs(str(mock_repo))) == snapshot


@pytest.mark.parametrize(
    ("mock_repo", "expected_value"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "go_repos", "no_go_mod"), False),
        # TODO: Having an extra go.mod breaks the pre-commit hooks; investigate a fix
        # (Path(__file__).parent.joinpath("mock_repos", "go_repos", "go_mod"), True),
    ],
)
def test_go_build_tool(go_tool: Go, macaron_path: str, mock_repo: str, expected_value: bool) -> None:
    """Test the Go build tool."""
    base_dir = Path(__file__).parent
    ctx = prepare_repo_for_testing(mock_repo, macaron_path, base_dir)
    assert go_tool.is_detected(ctx.component.repository.fs_path) == expected_value
