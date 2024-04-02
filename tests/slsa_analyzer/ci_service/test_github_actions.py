# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests GitHub Actions CI service."""

import os
from pathlib import Path

import pytest

from macaron import MACARON_PATH
from macaron.code_analyzer.call_graph import CallGraph
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
    root = GitHubWorkflowNode(name="root", node_type=GitHubWorkflowType.NONE, source_path="", parsed_obj={})
    gh_cg = CallGraph(root, "")
    workflow_path = os.path.join(resources_dir, workflow_name)
    parsed_obj = parse_action(workflow_path, macaron_path=MACARON_PATH)

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
