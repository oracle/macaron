# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the call graphs.
"""

import os
from pathlib import Path

import pytest

from macaron.code_analyzer.call_graph import CallGraph
from macaron.parsers.actionparser import parse as parse_action
from macaron.slsa_analyzer.ci_service.github_actions import GHWorkflowType, GitHubActions, GitHubNode

from ...macaron_testcase import MacaronTestCase


class TestGitHubActions(MacaronTestCase):
    """Test the GitHub Actions CI service."""

    github_actions = GitHubActions()
    mock_repos = Path(__file__).parent.joinpath("mock_repos")
    ga_has_build_kws = mock_repos.joinpath("has_build_gh_actions")
    jenkins_build = mock_repos.joinpath("has_build_jenkins")
    ga_no_build_kws = mock_repos.joinpath("no_build_gh_actions")

    def test_build_call_graph(self) -> None:
        """Test building call graphs for GitHub Actions workflows."""
        resources_dir = Path(__file__).parent.joinpath("resources", "github")

        # Test internal and reusable workflows.
        # Parse GitHub Actions workflows.
        root = GitHubNode(name="root", node_type=GHWorkflowType.NONE, source_path="", parsed_obj={}, caller_path="")
        gh_cg = CallGraph(root, "")
        workflow_path = os.path.join(resources_dir, "valid1.yaml")
        parsed_obj = parse_action(workflow_path, macaron_path=str(self.macaron_path))

        callee = GitHubNode(
            name=os.path.basename(workflow_path),
            node_type=GHWorkflowType.INTERNAL,
            source_path=workflow_path,
            parsed_obj=parsed_obj,
            caller_path="",
        )
        root.add_callee(callee)
        self.github_actions.build_call_graph_from_node(callee)
        assert [
            "GitHubNode(valid1.yaml,GHWorkflowType.INTERNAL)",
            "GitHubNode(apache/maven-gh-actions-shared/.github/workflows/maven-verify.yml@v2,GHWorkflowType.REUSABLE)",
        ] == [str(node) for node in gh_cg.bfs()]

        # Test internal and external workflows.
        # Parse GitHub Actions workflows.
        root = GitHubNode(name="root", node_type=GHWorkflowType.NONE, source_path="", parsed_obj={}, caller_path="")
        gh_cg = CallGraph(root, "")
        workflow_path = os.path.join(resources_dir, "valid2.yaml")
        parsed_obj = parse_action(workflow_path, macaron_path=str(self.macaron_path))

        callee = GitHubNode(
            name=os.path.basename(workflow_path),
            node_type=GHWorkflowType.INTERNAL,
            source_path=workflow_path,
            parsed_obj=parsed_obj,
            caller_path="",
        )
        root.add_callee(callee)
        self.github_actions.build_call_graph_from_node(callee)
        assert [
            "GitHubNode(valid2.yaml,GHWorkflowType.INTERNAL)",
            "GitHubNode(actions/checkout@v3,GHWorkflowType.EXTERNAL)",
            "GitHubNode(actions/cache@v3,GHWorkflowType.EXTERNAL)",
            "GitHubNode(actions/setup-java@v3,GHWorkflowType.EXTERNAL)",
        ] == [str(node) for node in gh_cg.bfs()]

    @pytest.mark.skip()
    def test_is_detected(self) -> None:
        """Test detecting GitHub Action config files."""
        assert self.github_actions.is_detected(str(self.ga_has_build_kws))
        assert self.github_actions.is_detected(str(self.ga_no_build_kws))
        assert not self.github_actions.is_detected(str(self.jenkins_build))

    def test_get_workflows(self) -> None:
        """Test getting GitHub Actions workflows."""
        expect = list(self.ga_has_build_kws.joinpath(".github", "workflows").glob("*")).sort()
        assert self.github_actions.get_workflows(str(self.ga_has_build_kws)).sort() == expect

        expect = list(self.ga_no_build_kws.joinpath(".github", "workflows").glob("*")).sort()
        assert self.github_actions.get_workflows(str(self.ga_no_build_kws)).sort() == expect

        assert not self.github_actions.get_workflows(str(self.jenkins_build))
