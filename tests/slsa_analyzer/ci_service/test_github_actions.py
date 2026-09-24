# Copyright (c) 2022 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests GitHub Actions CI service."""

import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from macaron.code_analyzer.dataflow_analysis import github
from macaron.code_analyzer.dataflow_analysis.core import traverse_bfs
from macaron.code_analyzer.gha_security_analysis.detect_injection import detect_github_actions_security_issues
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions

mock_repos = Path(__file__).parent.joinpath("mock_repos")
ga_has_build_kws = mock_repos.joinpath("has_build_gh_actions")
jenkins_build = mock_repos.joinpath("has_build_jenkins")
ga_no_build_kws = mock_repos.joinpath("no_build_gh_actions")


@pytest.fixture(name="github_actions")
def github_actions_() -> GitHubActions:
    """Create a GitHubActions instance."""
    return GitHubActions()


def test_is_detected(github_actions: GitHubActions) -> None:
    """Test detecting GitHub Action config files."""
    assert github_actions.is_detected(str(ga_has_build_kws))
    assert github_actions.is_detected(str(ga_no_build_kws))
    assert not github_actions.is_detected(str(jenkins_build))


@pytest.mark.parametrize(
    "mock_repo",
    [
        ga_has_build_kws,
        ga_no_build_kws,
    ],
    ids=[
        "GH Actions with build",
        "GH Actions with no build",
    ],
)
def test_gh_get_workflows(github_actions: GitHubActions, mock_repo: Path) -> None:
    """Test detection of reachable GitHub Actions workflows."""
    expect = [str(path) for path in mock_repo.joinpath(".github", "workflows").glob("*")]
    workflows = github_actions.get_workflows(str(mock_repo))
    assert sorted(workflows) == sorted(expect)


def test_gh_get_workflows_fail_on_jenkins(github_actions: GitHubActions) -> None:
    """Assert GitHubActions workflow detection not working on Jenkins CI configuration files."""
    assert not github_actions.get_workflows(str(jenkins_build))


def test_build_call_graph_expands_reachable_composite_actions(github_actions: GitHubActions, tmp_path: Path) -> None:
    """Nested steps in reachable local composite actions are included in the callgraph."""
    repo_path = tmp_path
    workflow_dir = repo_path.joinpath(".github", "workflows")
    action_dir = repo_path.joinpath(".github", "actions", "setup")
    workflow_dir.mkdir(parents=True)
    action_dir.mkdir(parents=True)
    workflow_path = workflow_dir.joinpath("ci.yml")
    workflow_path.write_text(
        """
name: ci
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/setup
""",
        encoding="utf-8",
    )
    action_dir.joinpath("action.yml").write_text(
        """
name: setup
runs:
  using: composite
  steps:
    - uses: actions/setup-node@v4
""",
        encoding="utf-8",
    )

    callgraph = github_actions.build_call_graph_for_files([str(workflow_path)], str(repo_path))

    action_steps = [
        node.uses_name
        for root in callgraph.root_nodes
        for node in traverse_bfs(root)
        if isinstance(node, github.GitHubActionsActionStepNode)
    ]
    assert action_steps == ["./.github/actions/setup", "actions/setup-node"]
    assert [finding["workflow_name"] for finding in detect_github_actions_security_issues(callgraph)] == [
        os.path.relpath(workflow_path, Path.cwd()),
    ]


def test_build_call_graph_adds_unreachable_composite_actions_as_roots(
    github_actions: GitHubActions, tmp_path: Path
) -> None:
    """Unreachable local composite actions are added as independent callgraph roots."""
    repo_path = tmp_path
    workflow_dir = repo_path.joinpath(".github", "workflows")
    action_dir = repo_path.joinpath(".github", "actions", "unused")
    workflow_dir.mkdir(parents=True)
    action_dir.mkdir(parents=True)
    workflow_path = workflow_dir.joinpath("ci.yml")
    workflow_path.write_text(
        """
name: ci
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
        encoding="utf-8",
    )
    action_path = action_dir.joinpath("action.yaml")
    action_path.write_text(
        """
name: unused
runs:
  using: composite
  steps:
    - uses: actions/cache@v4
""",
        encoding="utf-8",
    )

    callgraph = github_actions.build_call_graph_for_files([str(workflow_path)], str(repo_path))

    root_paths = [
        node.context.ref.source_filepath
        for root in callgraph.root_nodes
        for node in traverse_bfs(root)
        if isinstance(node, github.GitHubActionsWorkflowNode)
    ]
    assert root_paths == [str(workflow_path), str(action_path)]
    assert any(
        isinstance(node, github.GitHubActionsActionStepNode) and node.uses_name == "actions/cache"
        for root in callgraph.root_nodes
        for node in traverse_bfs(root)
    )


@pytest.mark.parametrize(
    ("started_at", "publish_date_time", "commit_date_time", "time_range", "expected"),
    [
        pytest.param(
            datetime.now(),
            datetime.now() - timedelta(hours=1),
            datetime.now() + timedelta(minutes=10),
            3600,
            False,
            id="Publish time before CI start time.",
        ),
        pytest.param(
            datetime.now(),
            datetime.now() + timedelta(hours=1),
            datetime.now() + timedelta(minutes=10),
            3600,
            True,
            id="Publish time 1h after CI run and source commit happened after CI trigger within acceptable range.",
        ),
        pytest.param(
            datetime.now() - timedelta(hours=1),
            datetime.now(),
            datetime.now() + timedelta(minutes=10),
            3600,
            False,
            id="Source commit occurred after the CI run and outside the acceptable time range.",
        ),
    ],
)
def test_check_publish_start_commit_timestamps(
    github_actions: GitHubActions,
    started_at: datetime,
    publish_date_time: datetime,
    commit_date_time: datetime,
    time_range: int,
    expected: bool,
) -> None:
    """Check that a CI run that has happened before the artifact publishing timestamp can be correctly identified."""
    assert (
        github_actions.check_publish_start_commit_timestamps(
            started_at, publish_date_time, commit_date_time, time_range
        )
        == expected
    )


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("2023-02-17T18:50:09+00:00", True),
        ("2000-02-17T18:50:09+00:00", True),
        ("3000-02-17T18:50:09+00:00", False),
    ],
)
def test_workflow_run_deleted(github_actions: GitHubActions, timestamp: str, expected: bool) -> None:
    """Test that deleted workflows can be detected."""
    timestamp_obj = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z")
    assert github_actions.workflow_run_deleted(timestamp=timestamp_obj) == expected
