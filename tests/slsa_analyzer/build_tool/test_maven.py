# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Maven build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
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
            ["mvn", "deploy"],
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
            ["mvn", "package"],
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
            ["mvn", "deploy"],
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
            ["mvn", "deploy"],
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
            ["mvn", "deploy"],
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
            ["mvn", "deploy"],
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
            ["mvn", "deploy"],
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
            ["mvn", "deploy"],
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
def test_is_maven_deploy_command(
    maven_tool: Maven,
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
    result, _ = maven_tool.is_deploy_command(
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
            ["mvn", "package"],
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
            ["mvn", "test"],
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
            ["mvn", "package"],
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
            ["mvn", "package"],
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
            ["mvn", "package"],
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
            ["mvn", "package"],
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
            ["mvn", "package"],
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
            ["mvn", "package"],
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
            ["mvn", "deploy"],
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
def test_is_maven_package_command(
    maven_tool: Maven,
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
    result, _ = maven_tool.is_package_command(
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
