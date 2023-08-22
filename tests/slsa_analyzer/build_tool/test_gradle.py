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


def test_get_group_ids_nested_projects(tmp_path: Path, gradle_tool: Gradle) -> None:
    """Test the ``get_group_ids`` method in case there are Gradle projects nested under a root project.

    In this case, we should only obtain the group id of the root project, making the assumption
    that all subprojects under it have the same group id.

    This is consistent with the behavior of the ``get_build_dirs`` method.
    """
    repo_dir = tmp_path.joinpath("repo")
    subproject_a_dir = repo_dir.joinpath("subprojecta")
    subproject_b_dir = repo_dir.joinpath("subprojectb")

    subproject_a_dir.mkdir(parents=True)
    subproject_b_dir.mkdir(parents=True)

    with open(repo_dir.joinpath("build.gradle"), "w", encoding="utf-8") as file:
        file.write('group = "io.micronaut"')
    with open(subproject_a_dir.joinpath("build.gradle"), "w", encoding="utf-8") as file:
        file.write('group = "io.micronaut.foo"')
    with open(subproject_b_dir.joinpath("build.gradle"), "w", encoding="utf-8") as file:
        file.write('group = "io.micronaut.bar"')

    assert set(gradle_tool.get_group_ids(str(repo_dir))) == {"io.micronaut"}


def test_get_group_ids_separate_projects(tmp_path: Path, gradle_tool: Gradle) -> None:
    """Test the ``get_group_ids`` method in case there are multiple separate Gradle projects in a repo.

    "Separate projects" means they are in different directories in the repo.
    """
    repo_dir = tmp_path.joinpath("repo")

    project_a_dir = repo_dir.joinpath("subprojecta")
    project_b_dir = repo_dir.joinpath("subprojectb")

    project_a_dir.mkdir(parents=True)
    project_b_dir.mkdir(parents=True)

    with open(project_a_dir.joinpath("build.gradle"), "w", encoding="utf-8") as file:
        file.write('group = "io.micronaut.foo"')
    with open(project_b_dir.joinpath("build.gradle"), "w", encoding="utf-8") as file:
        file.write('group = "io.micronaut.bar"')

    assert set(gradle_tool.get_group_ids(str(repo_dir))) == {
        "io.micronaut.foo",
        "io.micronaut.bar",
    }
