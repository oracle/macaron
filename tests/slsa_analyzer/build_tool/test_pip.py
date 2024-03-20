# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Pip build functions."""

import pytest

from macaron.code_analyzer.call_graph import BaseNode
from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from macaron.slsa_analyzer.build_tool.pip import Pip


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
            ["twine", "upload"],
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
            ".github/workflows/pip.yaml",
            [{"key", "pass"}],
            ["push"],
            ["pip.yaml"],
            False,
        ),
        (
            ["python", "-m", "twine", "upload"],
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
def test_is_pip_deploy_command(
    pip_tool: Pip,
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
    result, _ = pip_tool.is_deploy_command(
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
            ["pip", "build"],
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
            ["python", "-m", "pip", "build"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["python", "-m", "flit", "build"],
            BuildLanguage.PYTHON,
            None,
            None,
            ".github/workflows/build.yaml",
            [{"key", "pass"}],
            ["push"],
            None,
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
            ["pip", "install", "--upgrade", "pip"],
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
            ["pip", "build"],
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
def test_is_pip_package_command(
    pip_tool: Pip,
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
    result, _ = pip_tool.is_package_command(
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
