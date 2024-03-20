# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Gradle build functions."""

from pathlib import Path

import pytest

from macaron.code_analyzer.call_graph import BaseNode
from macaron.config.defaults import load_defaults
from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
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


@pytest.mark.parametrize(("timeout", "expected"), [("0", set()), ("invalid", {"io.micronaut"})])
def test_get_group_ids_timeout(tmp_path: Path, gradle_tool: Gradle, timeout: str, expected: set) -> None:
    """Test the timeout configuration on ``get_group_ids`` method."""
    repo_dir = tmp_path.joinpath("repo")
    repo_dir.mkdir()

    with open(repo_dir.joinpath("build.gradle"), "w", encoding="utf-8") as file:
        file.write('group = "io.micronaut"')

    user_config_path = str(tmp_path.joinpath("config.ini"))
    user_config_input = f"""
        [builder.gradle.runtime]
        build_timeout = {timeout}
    """
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)

    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)
    gradle_tool.load_defaults()

    assert set(gradle_tool.get_group_ids(str(repo_dir))) == expected


@pytest.mark.parametrize(
    (
        "command",
        "language",
        "language_versions",
        "language_distributions",
        "ci_path",
        "reachable_secrets",
        "events",
        "filter_configs",
        "expected_result",
    ),
    [
        (
            ["gradle", "publish"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["gradle", "build"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["codeql-analysis.yaml"],
            False,
        ),
        (
            ["gradle", "publish"],
            BuildLanguage.PYTHON,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["codeql-analysis.yaml"],
            False,
        ),
        (
            ["gradle", "publish"],
            BuildLanguage.JAVA,
            ["11", "17"],
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["gradle", "publish"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/maven.yaml",
            [{"key", "pass"}],
            ["push"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["gradle", "publish"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/release.yaml",
            [],
            ["push"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["gradle", "publish"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["gradle", "publish"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/maven.yaml",
            [{"key", "pass"}],
            ["push"],
            ["maven.yaml"],
            False,
        ),
        (
            ["npm", "publish"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/maven.yaml",
            [{"key", "pass"}],
            ["push"],
            ["maven.yaml"],
            False,
        ),
    ],
)
def test_is_gradle_deploy_command(
    gradle_tool: Gradle,
    command: list[str],
    language: str,
    language_versions: list[str],
    language_distributions: list[str],
    ci_path: str,
    reachable_secrets: list[str],
    events: list[str],
    filter_configs: list[str],
    expected_result: bool,
) -> None:
    """Test the deploy commend detection function."""
    result, _ = gradle_tool.is_deploy_command(
        BuildToolCommand(
            command=command,
            language=language,
            language_versions=language_versions,
            language_distributions=language_distributions,
            language_url=None,
            caller_path="",
            ci_path=ci_path,
            job_name="",
            step_node=BaseNode(),
            reachable_secrets=reachable_secrets,
            events=events,
        ),
        filter_configs=filter_configs,
    )
    assert result == expected_result


@pytest.mark.parametrize(
    (
        "command",
        "language",
        "language_versions",
        "language_distributions",
        "ci_path",
        "reachable_secrets",
        "events",
        "filter_configs",
        "expected_result",
    ),
    [
        (
            ["gradle", "build"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["gradle", "test"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["codeql-analysis.yaml"],
            False,
        ),
        (
            ["gradle", "build"],
            BuildLanguage.PYTHON,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["codeql-analysis.yaml"],
            False,
        ),
        (
            ["gradle", "build"],
            BuildLanguage.JAVA,
            ["11", "17"],
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["gradle", "build"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/maven.yaml",
            [{"key", "pass"}],
            ["push"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["gradle", "build"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/release.yaml",
            [],
            ["push"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["gradle", "build"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["gradle", "build"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/maven.yaml",
            [{"key", "pass"}],
            ["push"],
            ["maven.yaml"],
            False,
        ),
        (
            ["npm", "publish"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/maven.yaml",
            [{"key", "pass"}],
            ["push"],
            ["maven.yaml"],
            False,
        ),
        (
            ["gradle", "publish"],
            BuildLanguage.JAVA,
            ["11", "17"],
            ["temurin"],
            ".github/workflows/maven.yaml",
            [{"key", "pass"}],
            ["push"],
            ["maven.yaml"],
            False,
        ),
    ],
)
def test_is_gradle_package_command(
    gradle_tool: Gradle,
    command: list[str],
    language: str,
    language_versions: list[str],
    language_distributions: list[str],
    ci_path: str,
    reachable_secrets: list[str],
    events: list[str],
    filter_configs: list[str],
    expected_result: bool,
) -> None:
    """Test the packaging command detection function."""
    result, _ = gradle_tool.is_package_command(
        BuildToolCommand(
            command=command,
            language=language,
            language_versions=language_versions,
            language_distributions=language_distributions,
            language_url=None,
            caller_path="",
            ci_path=ci_path,
            job_name="",
            step_node=BaseNode(),
            reachable_secrets=reachable_secrets,
            events=events,
        ),
        filter_configs=filter_configs,
    )
    assert result == expected_result
