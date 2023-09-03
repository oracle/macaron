# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Go build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.go import Go
from tests.slsa_analyzer.mock_git_utils import prepare_repo_for_testing


@pytest.mark.parametrize(
    ("folder", "file"),
    [
        ("root_go_mod", "go.mod"),
        ("no_go_mod", "dummyfile.txt"),
    ],
)
def test_get_build_dirs(snapshot: list, tmp_path: Path, go_tool: Go, folder: str, file: str) -> None:
    """Test discovering build directories."""
    # Since there's issues having 2 go.mod files in the same project, we make
    # it on the fly for this test
    proj_dir = tmp_path.joinpath(folder)
    proj_dir.mkdir(parents=True)

    with open(proj_dir.joinpath(file), "w", encoding="utf-8"):
        assert list(go_tool.get_build_dirs(str(proj_dir))) == snapshot


@pytest.mark.parametrize(
    ("folder", "file", "expected_value"),
    [
        ("root_go_mod", "go.mod", True),
        ("no_go_mod", "dummyfile.txt", False),
    ],
)
def test_go_build_tool(
    go_tool: Go, macaron_path: str, tmp_path: Path, folder: str, file: str, expected_value: bool
) -> None:
    """Test the Go build tool."""
    base_dir = Path(__file__).parent

    # Since there's issues having 2 go.mod files in the same project, we make
    # it on the fly for this test
    proj_dir = tmp_path.joinpath(folder)
    proj_dir.mkdir(parents=True)

    with open(proj_dir.joinpath(file), "w", encoding="utf-8"):
        ctx = prepare_repo_for_testing(proj_dir, macaron_path, base_dir)
        assert go_tool.is_detected(ctx.component.repository.fs_path) == expected_value
