# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Build As Code Check."""

import os
from pathlib import Path
from typing import cast

import pytest

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.parsers.actionparser import parse as parse_action
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.pip import Pip
from macaron.slsa_analyzer.checks.build_as_code_check import BuildAsCodeCheck, BuildAsCodeFacts
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService
from macaron.slsa_analyzer.ci_service.github_actions.analyzer import (
    GitHubWorkflowNode,
    GitHubWorkflowType,
    build_call_graph_from_node,
)
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from macaron.slsa_analyzer.specs.inferred_provenance import Provenance
from tests.conftest import MockAnalyzeContext, build_github_actions_call_graph_for_commands


@pytest.mark.parametrize(
    ("build_tool_name", "ci_name", "expected_result"),
    [
        ("maven", "github_actions", CheckResultType.FAILED),
        ("gradle", "github_actions", CheckResultType.FAILED),
        ("poetry", "github_actions", CheckResultType.FAILED),
        ("pip", "github_actions", CheckResultType.FAILED),
        ("maven", "jenkins", CheckResultType.FAILED),
        ("maven", "travis_ci", CheckResultType.FAILED),
        ("maven", "circle_ci", CheckResultType.FAILED),
        ("maven", "gitlab_ci", CheckResultType.FAILED),
    ],
)
def test_build_as_code_check_no_callgraph(
    macaron_path: Path,
    build_tools: dict[str, BaseBuildTool],
    build_tool_name: str,
    ci_services: dict[str, BaseCIService],
    ci_name: str,
    expected_result: CheckResultType,
) -> None:
    """Test the Build As Code Check when no callgraph is built for the CI service."""
    ci_info = CIInfo(
        service=ci_services[ci_name],
        callgraph=CallGraph(BaseNode(), ""),
        provenance_assets=[],
        release={},
        provenances=[],
        build_info_results=InTotoV01Payload(statement=Provenance().payload),
    )
    use_build_tool = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    use_build_tool.dynamic_data["build_spec"]["tools"] = [build_tools[build_tool_name]]
    use_build_tool.dynamic_data["ci_services"] = [ci_info]

    check = BuildAsCodeCheck()
    assert check.run_check(use_build_tool).result_type == expected_result


def test_no_build_tool(macaron_path: Path) -> None:
    """Test the Build As Code Check when no build tools are found."""
    check = BuildAsCodeCheck()
    no_build_tool = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    no_build_tool.dynamic_data["build_spec"]["tools"] = []
    assert check.run_check(no_build_tool).result_type == CheckResultType.FAILED


@pytest.mark.parametrize(
    ("build_tool_name", "commands", "expected_result"),
    [
        ("maven", ["mvn deploy"], CheckResultType.PASSED),
        ("maven", ["./mvn deploy"], CheckResultType.PASSED),
        ("maven", ["mvn deployblah"], CheckResultType.FAILED),
        ("maven", ["mvn verify"], CheckResultType.FAILED),
        ("maven", ["mvnblah deploy"], CheckResultType.FAILED),
        ("maven", ["mvn install"], CheckResultType.FAILED),
        ("gradle", ["./gradlew publishToSonatype"], CheckResultType.PASSED),
        ("poetry", ["poetry publish"], CheckResultType.PASSED),
        ("poetry", ["poetry upload"], CheckResultType.FAILED),
        ("pip", ["twine upload dist/*"], CheckResultType.PASSED),
        ("pip", ["flit publish"], CheckResultType.PASSED),
    ],
)
def test_deploy_commands(
    macaron_path: Path,
    build_tools: dict[str, BaseBuildTool],
    github_actions_service: GitHubActions,
    build_tool_name: str,
    commands: list[str],
    expected_result: CheckResultType,
) -> None:
    """Test the Build As Code Check when with different build commands."""
    deploy_ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    deploy_ctx.dynamic_data["build_spec"]["tools"] = [build_tools[build_tool_name]]
    ci_info = CIInfo(
        service=github_actions_service,
        callgraph=build_github_actions_call_graph_for_commands(commands=commands),
        provenance_assets=[],
        release={},
        provenances=[],
        build_info_results=InTotoV01Payload(statement=Provenance().payload),
    )
    ci_info["service"] = github_actions_service
    deploy_ctx.dynamic_data["ci_services"] = [ci_info]
    check = BuildAsCodeCheck()
    assert check.run_check(deploy_ctx).result_type == expected_result


@pytest.mark.parametrize(
    ("workflow_name", "expected_result"),
    [
        pytest.param(
            "pypi_publish.yaml",
            CheckResultType.PASSED,
            id="Uses gh-action-pypi-publish to publish.",
        ),
        pytest.param(
            "pypi_publish_blah.yaml",
            CheckResultType.FAILED,
            id="Does not a trusted action to publish.",
        ),
    ],
)
def test_gha_workflow_deployment(
    macaron_path: Path,
    pip_tool: Pip,
    github_actions_service: GitHubActions,
    workflow_name: str,
    expected_result: CheckResultType,
) -> None:
    """Test the use of verified GitHub Actions to deploy."""
    check = BuildAsCodeCheck()
    ci_info = CIInfo(
        service=github_actions_service,
        callgraph=CallGraph(BaseNode(), ""),
        provenance_assets=[],
        release={},
        provenances=[],
        build_info_results=InTotoV01Payload(statement=Provenance().payload),
    )

    workflows_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "github", "workflow_files")

    # This GitHub Actions workflow uses gh-action-pypi-publish to publish the artifact.
    gha_deploy = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    gha_deploy.dynamic_data["build_spec"]["tools"] = [pip_tool]
    gha_deploy.dynamic_data["ci_services"] = [ci_info]

    root: BaseNode = BaseNode()
    gh_cg = CallGraph(root, "")
    workflow_path = os.path.join(workflows_dir, workflow_name)
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
    ci_info["callgraph"] = gh_cg
    assert check.run_check(gha_deploy).result_type == expected_result


@pytest.mark.parametrize(
    ("repo_path", "expect_result"),
    [
        (Path(__file__).parent.joinpath("resources", "build_as_code", "travis_ci_with_deploy"), CheckResultType.PASSED),
        (Path(__file__).parent.joinpath("resources", "build_as_code", "travis_ci_no_deploy"), CheckResultType.FAILED),
    ],
)
def test_travis_ci_deploy(
    macaron_path: Path, gradle_tool: Gradle, travis_service: Jenkins, repo_path: Path, expect_result: CheckResultType
) -> None:
    """Test the Gradle build tool."""
    check = BuildAsCodeCheck()

    ci_info = CIInfo(
        service=travis_service,
        callgraph=CallGraph(BaseNode(), ""),
        provenance_assets=[],
        release={},
        provenances=[],
        build_info_results=InTotoV01Payload(statement=Provenance().payload),
    )
    gradle_deploy = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    gradle_deploy.component.repository.fs_path = str(repo_path.absolute())
    gradle_deploy.dynamic_data["build_spec"]["tools"] = [gradle_tool]
    gradle_deploy.dynamic_data["ci_services"] = [ci_info]

    assert check.run_check(gradle_deploy).result_type == expect_result


def test_multibuild_facts_saved(
    macaron_path: str, maven_tool: BaseBuildTool, gradle_tool: BaseBuildTool, github_actions_service: BaseCIService
) -> None:
    """Test that facts for all build tools are saved in the results tables in multi-build tool scenarios."""
    check = BuildAsCodeCheck()
    ci_info = CIInfo(
        service=github_actions_service,
        callgraph=build_github_actions_call_graph_for_commands(["./gradlew publishToSonatype", "mvn deploy"]),
        provenance_assets=[],
        release={},
        provenances=[],
        build_info_results=InTotoV01Payload(statement=Provenance().payload),
    )

    multi_build = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    multi_build.dynamic_data["build_spec"]["tools"] = [gradle_tool, maven_tool]
    multi_build.dynamic_data["ci_services"] = [ci_info]
    check_result = check.run_check(multi_build)
    assert check_result.result_type == CheckResultType.PASSED
    # Check facts exist for both gradle and maven.
    existing_facts = [cast(BuildAsCodeFacts, f).build_tool_name for f in check_result.result_tables]
    assert gradle_tool.name in existing_facts
    assert maven_tool.name in existing_facts
