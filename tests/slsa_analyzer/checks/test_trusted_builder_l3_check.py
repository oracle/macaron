# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Trusted Builder Level three check."""

import os
from unittest.mock import MagicMock

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.parsers.actionparser import parse as parse_action
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.checks.trusted_builder_l3_check import TrustedBuilderL3Check
from macaron.slsa_analyzer.ci_service.github_actions import GHWorkflowType, GitHubActions, GitHubNode
from macaron.slsa_analyzer.specs.ci_spec import CIInfo

from ...macaron_testcase import MacaronTestCase


class MockGitHubActions(GitHubActions):
    """Mock the GitHubActions class."""

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        return "run_feedback"


class TestTrustedBuilderL3Check(MacaronTestCase):
    """Test the Build As Code Check."""

    def test_trusted_builder_l3_check(self) -> None:
        """Test the Build As Code Check."""
        check = TrustedBuilderL3Check()
        check_result = CheckResult(justification=[])  # type: ignore
        workflows_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "resources", "github", "workflow_files"
        )
        github_actions = MockGitHubActions()
        ci_info = CIInfo(
            service=github_actions,
            bash_commands=[],
            callgraph=CallGraph(BaseNode(), ""),
            provenance_assets=[],
            latest_release={},
            provenances=[],
        )
        ctx = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
        ctx.dynamic_data["ci_services"] = [ci_info]

        # This GitHub Actions workflow is using a trusted builder.
        root = GitHubNode(name="root", node_type=GHWorkflowType.NONE, source_path="", parsed_obj={}, caller_path="")
        gh_cg = CallGraph(root, "")
        workflow_path = os.path.join(workflows_dir, "slsa_verifier.yaml")
        parsed_obj = parse_action(workflow_path, macaron_path=str(MacaronTestCase.macaron_path))
        callee = GitHubNode(
            name=os.path.basename(workflow_path),
            node_type=GHWorkflowType.INTERNAL,
            source_path=workflow_path,
            parsed_obj=parsed_obj,
            caller_path="",
        )
        root.add_callee(callee)
        github_actions.build_call_graph_from_node(callee)
        ci_info["callgraph"] = gh_cg
        assert check.run_check(ctx, check_result) == CheckResultType.PASSED

        # This GitHub Actions workflow is not using a trusted builder.
        root = GitHubNode(name="root", node_type=GHWorkflowType.NONE, source_path="", parsed_obj={}, caller_path="")
        gh_cg = CallGraph(root, "")
        workflow_path = os.path.join(workflows_dir, "maven_build_itself.yml")
        parsed_obj = parse_action(workflow_path, macaron_path=str(MacaronTestCase.macaron_path))
        callee = GitHubNode(
            name=os.path.basename(workflow_path),
            node_type=GHWorkflowType.INTERNAL,
            source_path=os.path.join(workflows_dir, "maven_build_itself.yml"),
            parsed_obj=parsed_obj,
            caller_path="",
        )
        root.add_callee(callee)
        github_actions.build_call_graph_from_node(callee)
        ci_info["callgraph"] = gh_cg
        assert check.run_check(ctx, check_result) == CheckResultType.FAILED
