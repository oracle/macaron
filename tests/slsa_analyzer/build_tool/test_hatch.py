# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Hatch build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
from macaron.slsa_analyzer.build_tool.hatch import Hatch
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from tests.slsa_analyzer.mock_git_utils import prepare_repo_for_testing


@pytest.mark.parametrize(
    "mock_repo",
    [
        Path(__file__).parent.joinpath("mock_repos", "hatch_repos", "has_hatch_pyproject"),
        Path(__file__).parent.joinpath("mock_repos", "hatch_repos", "no_hatch"),
    ],
)
def test_get_build_dirs(snapshot: list, hatch_tool: Hatch, mock_repo: Path) -> None:
    """Test discovering build directories."""
    assert list(hatch_tool.get_build_dirs(str(mock_repo))) == snapshot


@pytest.mark.parametrize(
    ("mock_repo", "expected_value"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "hatch_repos", "has_hatch_pyproject"), True),
        (Path(__file__).parent.joinpath("mock_repos", "hatch_repos", "no_hatch"), False),
    ],
)
def test_hatch_build_tool(hatch_tool: Hatch, macaron_path: str, mock_repo: str, expected_value: bool) -> None:
    """Test the Hatch build tool."""
    base_dir = Path(__file__).parent
    ctx = prepare_repo_for_testing(mock_repo, macaron_path, base_dir)
    assert hatch_tool.is_detected(ctx.component.repository.fs_path) == expected_value


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
            ["hatch", "publish"],
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
            ["hatch", "publish"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/hatch.yaml",
            [{"key", "pass"}],
            ["push"],
            ["hatch.yaml"],
            False,
        ),
        (
            ["python", "-m", "hatch", "publish"],
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
            ["hatch", "publish"],
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
def test_is_hatch_deploy_command(
    hatch_tool: Hatch,
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
    result, _ = hatch_tool.is_deploy_command(
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
            ["hatch", "build"],
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
            ["python", "-m", "hatch", "build"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["hatch.yaml"],
            True,
        ),
        (
            ["python", "-m", "hatch", "build"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/hatch.yaml",
            [{"key", "pass"}],
            ["push"],
            ["hatch.yaml"],
            False,
        ),
        (
            ["hatch", "--version"],
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
            ["hatch", "build"],
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
def test_is_hatch_package_command(
    hatch_tool: Hatch,
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
    result, _ = hatch_tool.is_package_command(
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
