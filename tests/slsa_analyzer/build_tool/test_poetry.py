# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Poetry build functions."""

from pathlib import Path

import pytest

from macaron.code_analyzer.call_graph import BaseNode
from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
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
            ["poetry", "publish"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["poetry", "publish"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/poetry.yaml",
            [{"key", "pass"}],
            ["push"],
            ["poetry.yaml"],
            False,
        ),
        (
            ["python", "-m", "poetry", "publish"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["poetry", "publish"],
            BuildLanguage.JAVASCRIPT,
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
def test_is_poetry_deploy_command(
    poetry_tool: Poetry,
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
    result, _ = poetry_tool.is_deploy_command(
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
            ["poetry", "build"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["python", "-m", "poetry", "build"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["poetry.yaml"],
            True,
        ),
        (
            ["python", "-m", "poetry", "build"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/poetry.yaml",
            [{"key", "pass"}],
            ["push"],
            ["poetry.yaml"],
            False,
        ),
        (
            ["poetry", "--version"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            False,
        ),
        (
            ["poetry", "build"],
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
def test_is_poetry_package_command(
    poetry_tool: Poetry,
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
    result, _ = poetry_tool.is_package_command(
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
        filter_configs=filter_configs,
    )
    assert result == expected_result
