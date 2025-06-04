# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Go build functions."""

from pathlib import Path

import pytest

from macaron.code_analyzer.call_graph import BaseNode
from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
from macaron.slsa_analyzer.build_tool.go import Go
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from tests.slsa_analyzer.mock_git_utils import prepare_repo_for_testing


@pytest.mark.parametrize(
    ("folder", "file"),
    [
        ("root_go_mod", "go.mod"),
        ("no_go_mod", "dummyfile.txt"),
    ],
)
def test_get_build_dirs(snapshot: list, tmp_path: Path, go_tool: Go, folder: str, file: str) -> None:
    """Test discovering build directories."""
    # Since there's issues having 2 go.mod files in the same project, we make
    # it on the fly for this test.
    proj_dir = tmp_path.joinpath(folder)
    proj_dir.mkdir(parents=True)

    with open(proj_dir.joinpath(file), "w", encoding="utf-8"):
        assert list(go_tool.get_build_dirs(str(proj_dir))) == snapshot


@pytest.mark.parametrize(
    ("folder", "file", "expected_value"),
    [
        ("root_go_mod", "go.mod", True),
        ("no_go_mod", "dummyfile.txt", False),
    ],
)
def test_go_build_tool(
    go_tool: Go, macaron_path: str, tmp_path: Path, folder: str, file: str, expected_value: bool
) -> None:
    """Test the Go build tool."""
    base_dir = Path(__file__).parent

    # Making directories with a go.mod but no actual Go project seems to cause issues
    # for the pre-commit hooks (errors like go: warning: "./..." matched no packages);
    # as such it is easiest for this test to just create/delete the go.mod files
    # macaron looks for on the fly instead of managing a proper project within the mock repos.
    proj_dir = tmp_path.joinpath(folder)
    proj_dir.mkdir(parents=True)

    with open(proj_dir.joinpath(file), "w", encoding="utf-8"):
        ctx = prepare_repo_for_testing(proj_dir, macaron_path, base_dir)
        assert go_tool.is_detected(ctx.component.repository.fs_path) == expected_value


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
            ["goreleaser", "release"],
            BuildLanguage.GO,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["goreleaser", "release"],
            BuildLanguage.GO,
            None,
            None,
            ".github/workflows/go.yaml",
            [{"key", "pass"}],
            ["push"],
            ["go.yaml"],
            False,
        ),
        (
            ["goreleaser", "release"],
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
def test_is_go_deploy_command(
    go_tool: Go,
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
    result, _ = go_tool.is_deploy_command(
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
            ["go", "build"],
            BuildLanguage.GO,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            True,
        ),
        (
            ["go", "install"],
            BuildLanguage.GO,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["push"],
            ["go.yaml"],
            True,
        ),
        (
            ["go", "version"],
            BuildLanguage.GO,
            None,
            None,
            ".github/workflows/release.yaml",
            [{"key", "pass"}],
            ["release"],
            ["codeql-analysis.yaml"],
            False,
        ),
        (
            ["go", "build"],
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
def test_is_go_package_command(
    go_tool: Go,
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
    result, _ = go_tool.is_package_command(
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
