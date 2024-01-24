# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Fixtures for tests."""
from pathlib import Path
from typing import NoReturn

import pytest

from macaron.config.defaults import create_defaults, defaults, load_defaults
from macaron.database.table_definitions import Analysis, Component, Repository
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.build_tool.docker import Docker
from macaron.slsa_analyzer.build_tool.go import Go
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.build_tool.npm import NPM
from macaron.slsa_analyzer.build_tool.pip import Pip
from macaron.slsa_analyzer.build_tool.poetry import Poetry
from macaron.slsa_analyzer.build_tool.yarn import Yarn
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.github_actions import GitHubActions
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis

# We need to pass fixture names as arguments to maintain an order.
# pylint: disable=redefined-outer-name


@pytest.fixture()
def test_dir() -> Path:
    """Set the root test_dir path.

    Returns
    -------
    Path
        The root path to the test directory.
    """
    return Path(__file__).parent


@pytest.fixture()
def macaron_path() -> Path:
    """Set the Macaron path.

    Returns
    -------
    Path
        The Macaron path.
    """
    return Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def setup_test(test_dir: Path, macaron_path: Path) -> NoReturn:  # type: ignore
    """Set up the necessary values for the tests.

    Parameters
    ----------
    test_dir: Path
        Depends on test_dir fixture.
    macaron_path: Path
        Depends on macaron_path fixture.

    Returns
    -------
    NoReturn
    """
    # Load values from defaults.ini.
    if not test_dir.joinpath("defaults.ini").exists():
        create_defaults(str(test_dir), str(macaron_path))

    load_defaults(str(macaron_path))
    yield
    defaults.clear()


@pytest.fixture(autouse=True)
def maven_tool(setup_test) -> Maven:  # type: ignore # pylint: disable=unused-argument
    """Create a Maven tool instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Maven
        The Maven instance.
    """
    maven = Maven()
    maven.load_defaults()
    return maven


@pytest.fixture(autouse=True)
def gradle_tool(setup_test) -> Gradle:  # type: ignore # pylint: disable=unused-argument
    """Create a Gradle tool instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Gradle
        The Gradle instance.
    """
    gradle = Gradle()
    gradle.load_defaults()
    return gradle


@pytest.fixture(autouse=True)
def poetry_tool(setup_test) -> Poetry:  # type: ignore # pylint: disable=unused-argument
    """Create a Poetry tool instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Poetry
        The Poetry instance.
    """
    poetry = Poetry()
    poetry.load_defaults()
    return poetry


@pytest.fixture(autouse=True)
def pip_tool(setup_test) -> Pip:  # type: ignore # pylint: disable=unused-argument
    """Create a Pip tool instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Pip
        The Pip instance.
    """
    pip = Pip()
    pip.load_defaults()
    return pip


@pytest.fixture(autouse=True)
def docker_tool(setup_test) -> Docker:  # type: ignore # pylint: disable=unused-argument
    """Create a Docker tool instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Docker
        The Docker instance.
    """
    docker = Docker()
    docker.load_defaults()
    return docker


@pytest.fixture(autouse=True)
def npm_tool(setup_test) -> NPM:  # type: ignore # pylint: disable=unused-argument
    """Create a NPM tool instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    NPM
        The NPM instance.
    """
    npm = NPM()
    npm.load_defaults()
    return npm


@pytest.fixture(autouse=True)
def yarn_tool(setup_test) -> Yarn:  # type: ignore # pylint: disable=unused-argument
    """Create a Yarn tool instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Yarn
        The Yarn instance.
    """
    yarn = Yarn()
    yarn.load_defaults()
    return yarn


@pytest.fixture(autouse=True)
def go_tool(setup_test) -> Go:  # type: ignore # pylint: disable=unused-argument
    """Create a Go tool instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Go
        The Go instance.
    """
    go = Go()  # pylint: disable=invalid-name
    go.load_defaults()
    return go


@pytest.fixture(name="build_tools")
def get_build_tools(
    npm_tool: BaseBuildTool,
    yarn_tool: BaseBuildTool,
    go_tool: BaseBuildTool,
    maven_tool: BaseBuildTool,
    gradle_tool: BaseBuildTool,
    pip_tool: BaseBuildTool,
    poetry_tool: BaseBuildTool,
    docker_tool: BaseBuildTool,
) -> dict[str, BaseBuildTool]:
    """Create a dictionary to look up build tool fixtures.

    `pytest.mark.parametrize` does not accept fixtures as arguments. This fixture is created as
    a workaround to parametrize tests with build tool fixtures.
    """
    return {
        "npm": npm_tool,
        "yarn": yarn_tool,
        "go": go_tool,
        "maven": maven_tool,
        "gradle": gradle_tool,
        "pip": pip_tool,
        "poetry": poetry_tool,
        "docker": docker_tool,
    }


class MockGitHubActions(GitHubActions):
    """Mock the GitHubActions class."""

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str | None, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        return "run_feedback"


@pytest.fixture()
def github_actions_service(setup_test) -> GitHubActions:  # type: ignore # pylint: disable=unused-argument
    """Create a GitHub Actions service instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    GitHub Actions
        The GitHub Actions instance.
    """
    github_actions = MockGitHubActions()
    github_actions.load_defaults()
    return github_actions


@pytest.fixture()
def jenkins_service(setup_test):  # type: ignore # pylint: disable=unused-argument
    """Create a Jenkins service instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Jenkins
        The Jenkins instance.
    """
    jenkins = Jenkins()
    jenkins.load_defaults()
    return jenkins


@pytest.fixture()
def travis_service(setup_test):  # type: ignore # pylint: disable=unused-argument
    """Create a Travis CI service instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Travis
        The Travis CI instance.
    """
    travis = Travis()
    travis.load_defaults()
    return travis


@pytest.fixture()
def circle_ci_service(setup_test):  # type: ignore # pylint: disable=unused-argument
    """Create a CircleCI service instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    CircleCI
        The CircleCI instance.
    """
    circle_ci = CircleCI()
    circle_ci.load_defaults()
    return circle_ci


@pytest.fixture()
def gitlab_ci_service(setup_test):  # type: ignore # pylint: disable=unused-argument
    """Create a GitLabCI service instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    GitLabCI
        The GitLabCI instance.
    """
    gitlab_ci = GitLabCI()
    gitlab_ci.load_defaults()
    return gitlab_ci


class MockAnalyzeContext(AnalyzeContext):
    """This class initializes a Component for the AnalyzeContext."""

    def __init__(self, *args, **kwargs) -> None:  # type: ignore
        component = Component(
            purl="pkg:github.com/package-url/purl-spec@244fd47e07d1004f0aed9c",
            analysis=Analysis(),
            repository=Repository(complete_name="github.com/package-url/purl-spec", fs_path=""),
        )
        super().__init__(component, *args, **kwargs)
