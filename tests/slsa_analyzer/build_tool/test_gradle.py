# Copyright (c) 2023 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Gradle build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from tests.conftest import MockAnalyzeContext
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
    ctx = MockAnalyzeContext(macaron_path="", output_dir="", fs_path=str(mock_repo))
    assert list(gradle_tool.get_build_dirs(ctx.component)) == snapshot


@pytest.mark.parametrize(
    ("mock_repo", "expected_value"),
    [
        (
            Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "groovy_gradle"),
            [
                ("build.gradle", 1.0, None, "settings.gradle"),
                ("settings.gradle", 0.5, None, "settings.gradle"),
            ],
        ),
        (
            Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "kotlin_gradle"),
            [
                ("build.gradle.kts", 1.0, None, "settings.gradle.kts"),
                ("settings.gradle.kts", 0.5, None, "settings.gradle.kts"),
            ],
        ),
        (
            Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "no_gradle"),
            [],
        ),
    ],
)
def test_gradle_build_tool(
    gradle_tool: Gradle,
    macaron_path: str,
    mock_repo: str,
    expected_value: list[tuple[str, float, str | None, str | None]],
) -> None:
    """Test the Gradle build tool."""
    base_dir = Path(__file__).parent
    ctx = prepare_repo_for_testing(mock_repo, macaron_path, base_dir)
    assert gradle_tool.is_detected(ctx.component) == (expected_value)


def test_gradle_build_tool_with_group_artifact_validation(gradle_tool: Gradle, tmp_path: Path) -> None:
    """Test Gradle detection with explicit group/artifact validation."""
    gradle_repo = tmp_path.joinpath("gradle_repo")
    gradle_repo.mkdir()
    gradle_repo.joinpath("build.gradle").write_text("group = 'com.example'")
    gradle_repo.joinpath("settings.gradle").write_text("rootProject.name = 'sample-app'\ninclude 'project1'\n")

    ctx = MockAnalyzeContext(
        macaron_path="",
        output_dir="",
        fs_path=str(gradle_repo),
        purl="pkg:maven/com.example/sample-app@1.0.0",
    )
    detected = gradle_tool.is_detected(ctx.component)
    assert detected
    assert {item[0] for item in detected} == {"build.gradle", "settings.gradle"}
    assert {item[3] for item in detected} == {"settings.gradle"}

    ctx.component.name = "another-app"
    not_detected = gradle_tool.is_detected(ctx.component)
    assert {item[0] for item in not_detected} == {"build.gradle", "settings.gradle"}
    assert all(item[1] <= 0.1 for item in not_detected)


def test_gradle_build_tool_with_project_group_and_multimodule_name(gradle_tool: Gradle, tmp_path: Path) -> None:
    """Test Gradle detection with projectGroup and prefixed multimodule artifact names."""
    gradle_repo = tmp_path.joinpath("gradle_repo")
    gradle_repo.joinpath("test-junit5").mkdir(parents=True)
    gradle_repo.joinpath("build.gradle").write_text("plugins { id 'java' }\n")
    gradle_repo.joinpath("test-junit5", "build.gradle").write_text("plugins { id 'java' }\n")
    gradle_repo.joinpath("settings.gradle").write_text("rootProject.name = 'test-parent'\ninclude 'test-junit5'\n")
    gradle_repo.joinpath("gradle.properties").write_text("projectGroup=io.micronaut.test\nprojectVersion=4.5.0\n")

    ctx = MockAnalyzeContext(
        macaron_path="",
        output_dir="",
        fs_path=str(gradle_repo),
        purl="pkg:maven/io.micronaut.test/micronaut-test-junit5@1.0.0",
    )
    detected = gradle_tool.is_detected(ctx.component)
    assert detected
    assert detected[0][0] == "test-junit5/build.gradle"
    assert detected[0][3] == "settings.gradle"


def test_gradle_build_tool_with_dynamic_include_it_name(gradle_tool: Gradle, tmp_path: Path) -> None:
    """Test Gradle detection when modules are dynamically included via include(it.name)."""
    gradle_repo = tmp_path.joinpath("gradle_repo")
    gradle_repo.joinpath("acra-core").mkdir(parents=True)
    gradle_repo.joinpath("acra-http").mkdir(parents=True)
    gradle_repo.joinpath("gradle.properties").write_text("group=ch.acra\nversion=5.12.0\n", encoding="utf-8")
    gradle_repo.joinpath("settings.gradle.kts").write_text(
        "\n".join(
            [
                "rootDir.listFiles()?.forEach {",
                '    if (it.isDirectory && it.name.startsWith("acra") && it.list()?.contains("build.gradle.kts") == true) {',
                "        include(it.name)",
                "    }",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gradle_repo.joinpath("build.gradle.kts").write_text("plugins {}\n", encoding="utf-8")
    gradle_repo.joinpath("acra-core", "build.gradle.kts").write_text("plugins {}\n", encoding="utf-8")
    gradle_repo.joinpath("acra-http", "build.gradle.kts").write_text("plugins {}\n", encoding="utf-8")

    ctx = MockAnalyzeContext(
        macaron_path="",
        output_dir="",
        fs_path=str(gradle_repo),
        purl="pkg:maven/ch.acra/acra-core@5.12.0",
    )
    detected = gradle_tool.is_detected(ctx.component)
    assert detected
    assert detected[0][0] == "acra-core/build.gradle.kts"


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
    excluded_configs: list[str] | None,
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
    excluded_configs: list[str] | None,
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
            ci_path=ci_path,
            step_node=None,
            reachable_secrets=reachable_secrets,
            events=events,
        ),
        excluded_configs=excluded_configs,
    )
    assert result == expected_result
