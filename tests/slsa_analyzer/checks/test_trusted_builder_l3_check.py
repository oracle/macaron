# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Trusted Builder Level three check."""

import os
from pathlib import Path

import pytest

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.parsers.actionparser import parse as parse_action
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.trusted_builder_l3_check import TrustedBuilderL3Check
from macaron.slsa_analyzer.ci_service.github_actions.analyzer import (
    GitHubWorkflowNode,
    GitHubWorkflowType,
    build_call_graph_from_node,
)
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from macaron.slsa_analyzer.specs.inferred_provenance import Provenance
from tests.conftest import MockAnalyzeContext


@pytest.mark.parametrize(
    ("workflow_name", "expected_result"),
    [
        pytest.param(
            "slsa_verifier.yaml",
            CheckResultType.PASSED,
            id="Workflow is using a trusted builder.",
        ),
        pytest.param(
            "maven_build_itself.yml",
            CheckResultType.FAILED,
            id="Workflow is not using a trusted builder.",
        ),
    ],
)
def test_trusted_builder_l3_check(
    macaron_path: Path, github_actions_service: GitHubActions, workflow_name: str, expected_result: CheckResultType
) -> None:
    """Test trusted builder l3 Check."""
    check = TrustedBuilderL3Check()
    workflows_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "github", "workflow_files")
    ci_info = CIInfo(
        service=github_actions_service,
        callgraph=CallGraph(BaseNode(), ""),
        provenance_assets=[],
        release={},
        provenances=[],
        build_info_results=InTotoV01Payload(statement=Provenance().payload),
    )

    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.dynamic_data["ci_services"] = [ci_info]

    root: BaseNode = BaseNode()
    gh_cg = CallGraph(root, "")
    workflow_path = os.path.join(workflows_dir, workflow_name)
    parsed_obj = parse_action(workflow_path)
    callee = GitHubWorkflowNode(
        name=workflow_name,
        node_type=GitHubWorkflowType.INTERNAL,
        source_path=workflow_path,
        parsed_obj=parsed_obj,
        caller=root,
    )
    build_call_graph_from_node(callee, repo_path="")
    root.add_callee(callee)
    ci_info["callgraph"] = gh_cg
    assert check.run_check(ctx).result_type == expected_result
