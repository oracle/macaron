# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests GitHub Actions CI service."""

import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.parsers.actionparser import parse as parse_action
from macaron.slsa_analyzer.ci_service.github_actions.analyzer import (
    GitHubWorkflowNode,
    GitHubWorkflowType,
    build_call_graph_from_node,
)
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions

mock_repos = Path(__file__).parent.joinpath("mock_repos")
ga_has_build_kws = mock_repos.joinpath("has_build_gh_actions")
jenkins_build = mock_repos.joinpath("has_build_jenkins")
ga_no_build_kws = mock_repos.joinpath("no_build_gh_actions")


@pytest.fixture(name="github_actions")
def github_actions_() -> GitHubActions:
    """Create a GitHubActions instance."""
    return GitHubActions()


@pytest.mark.parametrize(
    (
        "workflow_name",
        "expect",
    ),
    [
        (
            "valid1.yaml",
            [
                "GitHubWorkflowNode(valid1.yaml,GitHubWorkflowType.INTERNAL)",
                "GitHubJobNode(build)",
                "GitHubWorkflowNode(apache/maven-gh-actions-shared/.github/workflows/maven-verify.yml@v2,GitHubWorkflowType.REUSABLE)",
            ],
        ),
        (
            "valid2.yaml",
            [
                "GitHubWorkflowNode(valid2.yaml,GitHubWorkflowType.INTERNAL)",
                "GitHubJobNode(build)",
                "GitHubWorkflowNode(actions/checkout@v3,GitHubWorkflowType.EXTERNAL)",
                "GitHubWorkflowNode(actions/cache@v3,GitHubWorkflowType.EXTERNAL)",
                "GitHubWorkflowNode(actions/setup-java@v3,GitHubWorkflowType.EXTERNAL)",
                "BashNode(Publish to Sonatype Snapshots,BashScriptType.INLINE)",
            ],
        ),
    ],
    ids=[
        "Internal and reusable workflows",
        "Internal and external workflows",
    ],
)
def test_build_call_graph(workflow_name: str, expect: list[str]) -> None:
    """Test building call graphs for GitHub Actions workflows."""
    resources_dir = Path(__file__).parent.joinpath("resources", "github")

    # Parse GitHub Actions workflows.
    root: BaseNode = BaseNode()
    gh_cg = CallGraph(root, "")
    workflow_path = os.path.join(resources_dir, workflow_name)
    parsed_obj = parse_action(workflow_path)

    callee = GitHubWorkflowNode(
        name=os.path.basename(workflow_path),
        node_type=GitHubWorkflowType.INTERNAL,
        source_path=workflow_path,
        parsed_obj=parsed_obj,
        caller=root,
    )
    root.add_callee(callee)
    build_call_graph_from_node(callee, repo_path="")
    assert [str(node) for node in gh_cg.bfs()] == expect


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
