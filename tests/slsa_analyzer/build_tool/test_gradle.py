# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Gradle build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.gradle import Gradle
from tests.slsa_analyzer.mock_git_utils import prepare_repo_for_testing


@pytest.mark.parametrize(
    "mock_repo",
    [
        Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "groovy_gradle"),
        Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "kotlin_gradle"),
        Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "no_gradle"),
    ],
)
def test_get_build_dirs(snapshot: list, gradle_tool: Gradle, mock_repo: Path) -> None:
    """Test discovering build directories."""
    assert list(gradle_tool.get_build_dirs(str(mock_repo))) == snapshot


@pytest.mark.parametrize(
    ("mock_repo", "expected_value"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "groovy_gradle"), True),
        (Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "kotlin_gradle"), True),
        (Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "no_gradle"), False),
    ],
)
def test_gradle_build_tool(gradle_tool: Gradle, macaron_path: str, mock_repo: str, expected_value: bool) -> None:
    """Test the Gradle build tool."""
    base_dir = Path(__file__).parent
    ctx = prepare_repo_for_testing(mock_repo, macaron_path, base_dir)
    assert gradle_tool.is_detected(ctx.component.repository.fs_path) == expected_value
