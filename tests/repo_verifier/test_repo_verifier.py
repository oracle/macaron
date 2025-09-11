# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the repo verifier."""
from pathlib import Path

import pytest

from macaron.repo_verifier.repo_verifier_gradle import RepoVerifierGradle
from macaron.repo_verifier.repo_verifier_maven import RepoVerifierMaven
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool


def gradle_repo_verifier(build_tool: BaseBuildTool, mock_repo: str) -> RepoVerifierGradle:
    """
    Create and return an instance of RepoVerifierGradle with predefined test parameters.

    Parameters
    ----------
    build_tool: BaseBuildTool
        The build tool instance to be used for verification (expected to be Gradle).
    mock_repo: str
        File system path to the mock Gradle repository.

    Returns
    -------
    RepoVerifierGradle
        An initialized verifier for the provided mock Gradle repository.
    """
    return RepoVerifierGradle(
        namespace="com.example",
        name="artifact",
        version="1.0.0",
        reported_repo_url="https://github.com/example/example",
        reported_repo_fs=mock_repo,
        build_tool=build_tool,
        provenance_repo_url=None,
    )


def maven_repo_verifier(build_tool: BaseBuildTool, mock_repo: str) -> RepoVerifierMaven:
    """
    Create and return an instance of RepoVerifierMaven with predefined test parameters.

    Parameters
    ----------
    build_tool : BaseBuildTool
        The build tool instance to be used for verification (expected to be Maven).
    mock_repo : str
        File system path to the mock Maven repository.

    Returns
    -------
    RepoVerifierMaven
        A RepoVerifierMaven instance initialized with test parameters for the specified mock repo.
    """
    return RepoVerifierMaven(
        namespace="com.example",
        name="artifact",
        version="1.0.0",
        reported_repo_url="https://github.com/example/example",
        reported_repo_fs=mock_repo,
        build_tool=build_tool,
        provenance_repo_url=None,
    )


@pytest.mark.parametrize(
    ("mock_repo", "expected_result"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "fail_groovy"), False),
        (Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "pass_groovy"), True),
    ],
)
def test_extract_group_id_from_build_groovy(
    build_tools: dict[str, BaseBuildTool], mock_repo: Path, expected_result: bool
) -> None:
    """Test if the method successfully extracts a group ID from a given Gradle build (Groovy).

    Each test case provides a path to a mock repository and the expected boolean result: True if a group ID
    should be detected, False otherwise.
    """
    verifier = gradle_repo_verifier(build_tools["gradle"], str(mock_repo))
    assert (verifier.extract_group_id_from_build_groovy() is not None) == expected_result


@pytest.mark.parametrize(
    ("mock_repo", "expected_result"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "fail_properties"), False),
        (Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "pass_properties"), True),
    ],
)
def test_extract_group_id_from_build_properties(
    build_tools: dict[str, BaseBuildTool], mock_repo: Path, expected_result: bool
) -> None:
    """Test if the method successfully extracts a group ID from a given Gradle build (properties file).

    Each test case provides a path to a mock repository and the expected boolean result: True if a group ID
    should be detected, False otherwise.
    """
    verifier = gradle_repo_verifier(build_tools["gradle"], str(mock_repo))
    assert (verifier.extract_group_id_from_properties() is not None) == expected_result


@pytest.mark.parametrize(
    ("mock_repo", "expected_result"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "fail_kotlin"), False),
        (Path(__file__).parent.joinpath("mock_repos", "gradle_repos", "pass_kotlin"), True),
    ],
)
def test_extract_group_id_from_build_kotlin(
    build_tools: dict[str, BaseBuildTool], mock_repo: Path, expected_result: bool
) -> None:
    """Test if the method successfully extracts a group ID from a given Gradle build (Kotlin).

    Each test case provides a path to a mock repository and the expected boolean result: True if a group ID
    should be detected, False otherwise.
    """
    verifier = gradle_repo_verifier(build_tools["gradle"], str(mock_repo))
    assert (verifier.extract_group_id_from_build_kotlin() is not None) == expected_result


@pytest.mark.parametrize(
    ("mock_repo", "expected_result"),
    [
        (Path(__file__).parent.joinpath("mock_repos", "maven_repos", "fail_pom"), False),
        (Path(__file__).parent.joinpath("mock_repos", "maven_repos", "pass_pom"), True),
    ],
)
def test_extract_group_id_from_pom(
    build_tools: dict[str, BaseBuildTool], mock_repo: Path, expected_result: bool
) -> None:
    """Test if the method successfully extracts a group ID from a given Maven build.

    Each test case provides a path to a mock repository and the expected boolean result: True if a group ID
    should be detected, False otherwise.
    """
    verifier = maven_repo_verifier(build_tools["maven"], str(mock_repo))
    assert (verifier.extract_group_id_from_pom() is not None) == expected_result
