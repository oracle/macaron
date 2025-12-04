# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Docker build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
from macaron.slsa_analyzer.build_tool.docker import Docker
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from tests.slsa_analyzer.mock_git_utils import prepare_repo_for_testing


@pytest.mark.parametrize(
    "mock_repo",
    [
        Path(__file__).parent.joinpath("mock_repos", "docker_repos", "root_dockerfile"),
        Path(__file__).parent.joinpath("mock_repos", "docker_repos", "nested_dockerfile"),
        Path(__file__).parent.joinpath("mock_repos", "docker_repos", "root_wildcard_dockerfile"),
        Path(__file__).parent.joinpath("mock_repos", "docker_repos", "root_dockerfile_wildcard"),
        Path(__file__).parent.joinpath("mock_repos", "docker_repos", "no_docker"),
    ],
)
def test_get_build_dirs(snapshot: list, docker_tool: Docker, mock_repo: Path) -> None:
    """Test discovering build directories."""
    assert list(docker_tool.get_build_dirs(str(mock_repo))) == snapshot


@pytest.mark.parametrize(
    ("mock_repo", "expected_value"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "docker_repos", "root_dockerfile"), True),
        (Path(__file__).parent.joinpath("mock_repos", "docker_repos", "nested_dockerfile"), True),
        (Path(__file__).parent.joinpath("mock_repos", "docker_repos", "root_wildcard_dockerfile"), True),
        (Path(__file__).parent.joinpath("mock_repos", "docker_repos", "root_dockerfile_wildcard"), True),
        (Path(__file__).parent.joinpath("mock_repos", "docker_repos", "no_docker"), False),
    ],
)
def test_docker_build_tool(docker_tool: Docker, macaron_path: str, mock_repo: str, expected_value: bool) -> None:
    """Test the Docker build tool."""
    base_dir = Path(__file__).parent
    ctx = prepare_repo_for_testing(mock_repo, macaron_path, base_dir)
    assert docker_tool.is_detected(ctx.component.repository.fs_path) == expected_value


@pytest.mark.parametrize(
    (
        "command",
        "language",
        "language_versions",
        "language_distributions",
        "ci_path",
        "reachable_secrets",
        "events",
        "excluded_configs",
        "expected_result",
    ),
    [
        (
            ["docker", "push"],
            BuildLanguage.DOCKER,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["docker", "push"],
            BuildLanguage.DOCKER,
            None,
            None,
            ".github/workflows/docker.yaml",
            [{"key", "pass"}],
            ["push"],
            ["docker.yaml"],
            False,
        ),
        (
            ["docker", "build"],
            BuildLanguage.DOCKER,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            False,
        ),
        (
            ["docker", "push"],
            BuildLanguage.JAVA,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            None,
            False,
        ),
    ],
)
def test_is_docker_deploy_command(
    docker_tool: Docker,
    command: list[str],
    language: str,
    language_versions: list[str],
    language_distributions: list[str],
    ci_path: str,
    reachable_secrets: list[str],
    events: list[str],
    excluded_configs: list[str] | None,
    expected_result: bool,
) -> None:
    """Test the deploy commend detection function."""
    result, _ = docker_tool.is_deploy_command(
        BuildToolCommand(
            command=command,
            language=language,
            language_versions=language_versions,
            language_distributions=language_distributions,
            language_url=None,
            ci_path=ci_path,
            step_node=None,
            reachable_secrets=reachable_secrets,
            events=events,
        ),
        excluded_configs=excluded_configs,
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
        "excluded_configs",
        "expected_result",
    ),
    [
        (
            ["docker", "build"],
            BuildLanguage.DOCKER,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["docker", "build"],
            BuildLanguage.DOCKER,
            None,
            None,
            ".github/workflows/docker.yaml",
            [{"key", "pass"}],
            ["push"],
            ["docker.yaml"],
            False,
        ),
        (
            ["docker", "test"],
            BuildLanguage.DOCKER,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            False,
        ),
        (
            ["docker", "build"],
            BuildLanguage.JAVA,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            None,
            False,
        ),
    ],
)
def test_is_docker_package_command(
    docker_tool: Docker,
    command: list[str],
    language: str,
    language_versions: list[str],
    language_distributions: list[str],
    ci_path: str,
    reachable_secrets: list[str],
    events: list[str],
    excluded_configs: list[str] | None,
    expected_result: bool,
) -> None:
    """Test the packaging command detection function."""
    result, _ = docker_tool.is_package_command(
        BuildToolCommand(
            command=command,
            language=language,
            language_versions=language_versions,
            language_distributions=language_distributions,
            language_url=None,
            ci_path=ci_path,
            step_node=None,
            reachable_secrets=reachable_secrets,
            events=events,
        ),
        excluded_configs=excluded_configs,
    )
    assert result == expected_result
