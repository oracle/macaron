# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests GitHub Actions CI service."""

import os
from pathlib import Path

import pytest

from macaron import MACARON_PATH
from macaron.code_analyzer.call_graph import CallGraph
from macaron.parsers.actionparser import parse as parse_action
from macaron.slsa_analyzer.ci_service.github_actions import GHWorkflowType, GitHubActions, GitHubNode

mock_repos = Path(__file__).parent.joinpath("mock_repos")
ga_has_build_kws = mock_repos.joinpath("has_build_gh_actions")
jenkins_build = mock_repos.joinpath("has_build_jenkins")
ga_no_build_kws = mock_repos.joinpath("no_build_gh_actions")


@pytest.fixture(name="github_actions")
def github_actions_() -> GitHubActions:
    """Create a GitHubActions instance."""
    return GitHubActions()


def test_build_call_graph(github_actions: GitHubActions) -> None:
    """Test building call graphs for GitHub Actions workflows."""
    resources_dir = Path(__file__).parent.joinpath("resources", "github")

    # Test internal and reusable workflows.
    # Parse GitHub Actions workflows.
    root = GitHubNode(name="root", node_type=GHWorkflowType.NONE, source_path="", parsed_obj={}, caller_path="")
    gh_cg = CallGraph(root, "")
    workflow_path = os.path.join(resources_dir, "valid1.yaml")
    parsed_obj = parse_action(workflow_path, macaron_path=MACARON_PATH)

    callee = GitHubNode(
        name=os.path.basename(workflow_path),
        node_type=GHWorkflowType.INTERNAL,
        source_path=workflow_path,
        parsed_obj=parsed_obj,
        caller_path="",
    )
    root.add_callee(callee)
    github_actions.build_call_graph_from_node(callee)
    assert [
        "GitHubNode(valid1.yaml,GHWorkflowType.INTERNAL)",
        "GitHubNode(apache/maven-gh-actions-shared/.github/workflows/maven-verify.yml@v2,GHWorkflowType.REUSABLE)",
    ] == [str(node) for node in gh_cg.bfs()]

    # Test internal and external workflows.
    # Parse GitHub Actions workflows.
    root = GitHubNode(name="root", node_type=GHWorkflowType.NONE, source_path="", parsed_obj={}, caller_path="")
    gh_cg = CallGraph(root, "")
    workflow_path = os.path.join(resources_dir, "valid2.yaml")
    parsed_obj = parse_action(workflow_path, macaron_path=MACARON_PATH)

    callee = GitHubNode(
        name=os.path.basename(workflow_path),
        node_type=GHWorkflowType.INTERNAL,
        source_path=workflow_path,
        parsed_obj=parsed_obj,
        caller_path="",
    )
    root.add_callee(callee)
    github_actions.build_call_graph_from_node(callee)
    assert [
        "GitHubNode(valid2.yaml,GHWorkflowType.INTERNAL)",
        "GitHubNode(actions/checkout@v3,GHWorkflowType.EXTERNAL)",
        "GitHubNode(actions/cache@v3,GHWorkflowType.EXTERNAL)",
        "GitHubNode(actions/setup-java@v3,GHWorkflowType.EXTERNAL)",
    ] == [str(node) for node in gh_cg.bfs()]


def test_is_detected(github_actions: GitHubActions) -> None:
    """Test detecting GitHub Action config files."""
    assert github_actions.is_detected(str(ga_has_build_kws))
    assert github_actions.is_detected(str(ga_no_build_kws))
    assert not github_actions.is_detected(str(jenkins_build))


def test_get_workflows(github_actions: GitHubActions) -> None:
    """Test detection of reachable GitHub Actions workflows."""
    # Test GitHub Actions workflows that contain build commands.
    expect = [str(path) for path in ga_has_build_kws.joinpath(".github", "workflows").glob("*")]
    expect.sort()
    workflows = github_actions.get_workflows(str(ga_has_build_kws))
    workflows.sort()
    assert workflows == expect

    # Test GitHub Actions workflows that do not contain build commands.
    expect = [str(path) for path in ga_no_build_kws.joinpath(".github", "workflows").glob("*")]
    expect.sort()
    workflows = github_actions.get_workflows(str(ga_no_build_kws))
    workflows.sort()
    assert workflows == expect

    # The GitHubActions workflow detection should not work on Jenkins CI configuration files.
    assert not github_actions.get_workflows(str(jenkins_build))
