# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Flit build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
from macaron.slsa_analyzer.build_tool.flit import Flit
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from tests.slsa_analyzer.mock_git_utils import prepare_repo_for_testing


@pytest.mark.parametrize(
    "mock_repo",
    [
        Path(__file__).parent.joinpath("mock_repos", "flit_repos", "has_flit_pyproject"),
        Path(__file__).parent.joinpath("mock_repos", "flit_repos", "no_flit"),
    ],
)
def test_get_build_dirs(snapshot: list, flit_tool: Flit, mock_repo: Path) -> None:
    """Test discovering build directories."""
    assert list(flit_tool.get_build_dirs(str(mock_repo))) == snapshot


@pytest.mark.parametrize(
    ("mock_repo", "expected_value"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "flit_repos", "has_flit_pyproject"), True),
        (Path(__file__).parent.joinpath("mock_repos", "flit_repos", "no_flit"), False),
    ],
)
def test_flit_build_tool(flit_tool: Flit, macaron_path: str, mock_repo: str, expected_value: bool) -> None:
    """Test the Flit build tool."""
    base_dir = Path(__file__).parent
    ctx = prepare_repo_for_testing(mock_repo, macaron_path, base_dir)
    assert flit_tool.is_detected(ctx.component.repository.fs_path) == expected_value


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
            ["flit", "publish"],
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
            ["flit", "publish"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/flit.yaml",
            [{"key", "pass"}],
            ["push"],
            ["flit.yaml"],
            False,
        ),
        (
            ["python", "-m", "flit", "publish"],
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
            ["flit", "publish"],
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
def test_is_flit_deploy_command(
    flit_tool: Flit,
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
    result, _ = flit_tool.is_deploy_command(
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
            ["flit", "build"],
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
            ["python", "-m", "flit", "build"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["flit.yaml"],
            True,
        ),
        (
            ["python", "-m", "flit", "build"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/flit.yaml",
            [{"key", "pass"}],
            ["push"],
            ["flit.yaml"],
            False,
        ),
        (
            ["flit", "--version"],
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
            ["flit", "build"],
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
def test_is_flit_package_command(
    flit_tool: Flit,
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
    result, _ = flit_tool.is_package_command(
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
