# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the NPM build functions."""

from pathlib import Path

import pytest

from macaron.code_analyzer.call_graph import BaseNode
from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
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
    """Test the NPM build tool."""
    base_dir = Path(__file__).parent
    ctx = prepare_repo_for_testing(mock_repo, macaron_path, base_dir)
    assert npm_tool.is_detected(ctx.component.repository.fs_path) == expected_value


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
            ["npm", "publish"],
            BuildLanguage.JAVASCRIPT,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["npm", "publish"],
            BuildLanguage.JAVASCRIPT,
            None,
            None,
            ".github/workflows/npm.yaml",
            [{"key", "pass"}],
            ["push"],
            ["npm.yaml"],
            False,
        ),
        (
            ["npm", "run", "build"],
            BuildLanguage.JAVASCRIPT,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            False,
        ),
        (
            ["npm", "publish"],
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
def test_is_npm_deploy_command(
    npm_tool: NPM,
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
    result, _ = npm_tool.is_deploy_command(
        BuildToolCommand(
            command=command,
            language=language,
            language_versions=language_versions,
            language_distributions=language_distributions,
            language_url=None,
            ci_path=ci_path,
            step_node=BaseNode(),
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
            ["npm", "run", "build"],
            BuildLanguage.JAVASCRIPT,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["npm", "run", "build"],
            BuildLanguage.JAVASCRIPT,
            None,
            None,
            ".github/workflows/npm.yaml",
            [{"key", "pass"}],
            ["push"],
            ["npm.yaml"],
            False,
        ),
        (
            ["npm", "test"],
            BuildLanguage.JAVASCRIPT,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            False,
        ),
        (
            ["npm", "run", "build"],
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
def test_is_npm_package_command(
    npm_tool: NPM,
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
    result, _ = npm_tool.is_package_command(
        BuildToolCommand(
            command=command,
            language=language,
            language_versions=language_versions,
            language_distributions=language_distributions,
            language_url=None,
            ci_path=ci_path,
            step_node=BaseNode(),
            reachable_secrets=reachable_secrets,
            events=events,
        ),
        excluded_configs=excluded_configs,
    )
    assert result == expected_result
