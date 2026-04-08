# Copyright (c) 2023 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Maven build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from macaron.slsa_analyzer.build_tool.maven import Maven
from tests.conftest import MockAnalyzeContext
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
    ctx = MockAnalyzeContext(macaron_path="", output_dir="", fs_path=str(mock_repo))
    assert list(maven_tool.get_build_dirs(ctx.component)) == snapshot


@pytest.mark.parametrize(
    ("mock_repo", "group_id", "artifact_id", "expected_value"),
    [
        (
            Path(__file__).parent.joinpath("mock_repos", "maven_repos", "has_parent_pom"),
            "com.mock_repos.has_parent_pom",
            "sub_module_1",
            [("sub_module_1/pom.xml", 1.0, None, "pom.xml")],
        ),
        (
            Path(__file__).parent.joinpath("mock_repos", "maven_repos", "no_parent_pom"),
            "com.mock_repos.has_parent_pom",
            "sub_module_1",
            [
                ("sub_module_1/pom.xml", 0.1, None, None),
                ("sub_module_2/pom.xml", 0.05, None, None),
            ],
        ),
        (
            Path(__file__).parent.joinpath("mock_repos", "maven_repos", "no_pom"),
            "com.mock_repos.has_parent_pom",
            "sub_module_1",
            [],
        ),
    ],
)
def test_maven_build_tool(
    maven_tool: Maven,
    macaron_path: str,
    mock_repo: str,
    group_id: str,
    artifact_id: str,
    expected_value: list[tuple[str, float, str | None, str | None]],
) -> None:
    """Test the Maven build tool."""
    base_dir = Path(__file__).parent
    ctx = prepare_repo_for_testing(mock_repo, macaron_path, base_dir)
    ctx.component.type = maven_tool.purl_type
    ctx.component.namespace = group_id
    ctx.component.name = artifact_id
    assert maven_tool.is_detected(ctx.component) == expected_value


def test_maven_build_tool_with_group_artifact_validation(maven_tool: Maven, macaron_path: str) -> None:
    """Test Maven detection with explicit group/artifact validation."""
    base_dir = Path(__file__).parent
    mock_repo = Path(__file__).parent.joinpath("mock_repos", "maven_repos", "has_parent_pom")
    ctx = prepare_repo_for_testing(str(mock_repo), macaron_path, base_dir)
    ctx.component.type = maven_tool.purl_type
    ctx.component.namespace = "com.mock_repos.has_parent_pom"
    ctx.component.name = "sub_module_1"

    detected = maven_tool.is_detected(ctx.component)
    assert detected
    assert {item[0] for item in detected} == {"sub_module_1/pom.xml"}
    assert {item[3] for item in detected} == {"pom.xml"}

    ctx.component.name = "does-not-exist"
    not_detected = maven_tool.is_detected(ctx.component)
    assert {item[0] for item in not_detected} == {"pom.xml", "sub_module_1/pom.xml", "sub_module_2/pom.xml"}
    assert all(item[1] <= 0.1 for item in not_detected)


def test_maven_build_tool_with_multimodule_artifact_suffix(maven_tool: Maven, tmp_path: Path) -> None:
    """Test Maven detection with prefixed multi-module artifact ids."""
    maven_repo = tmp_path.joinpath("maven_repo")
    maven_repo.joinpath("test-junit5").mkdir(parents=True)
    maven_repo.joinpath("pom.xml").write_text(
        "\n".join(
            [
                "<project>",
                "  <modelVersion>4.0.0</modelVersion>",
                "  <groupId>io.micronaut.test</groupId>",
                "  <artifactId>test-parent</artifactId>",
                "  <version>1.0.0</version>",
                "  <packaging>pom</packaging>",
                "  <modules>",
                "    <module>test-junit5</module>",
                "  </modules>",
                "</project>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    maven_repo.joinpath("test-junit5", "pom.xml").write_text(
        "\n".join(
            [
                "<project>",
                "  <modelVersion>4.0.0</modelVersion>",
                "  <parent>",
                "    <groupId>io.micronaut.test</groupId>",
                "    <artifactId>test-parent</artifactId>",
                "    <version>1.0.0</version>",
                "    <relativePath>../</relativePath>",
                "  </parent>",
                "  <artifactId>micronaut-test-junit5</artifactId>",
                "</project>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    ctx = MockAnalyzeContext(
        macaron_path="",
        output_dir="",
        fs_path=str(maven_repo),
        purl="pkg:maven/io.micronaut.test/micronaut-test-junit5@1.0.0",
    )
    detected = maven_tool.is_detected(ctx.component)

    assert detected
    assert detected[0][0] == "test-junit5/pom.xml"
    assert detected[0][3] == "pom.xml"


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
