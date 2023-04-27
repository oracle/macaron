# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Build As Code Check."""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import macaron
from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.parsers.actionparser import parse as parse_action
from macaron.parsers.bashparser import BashCommands
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.build_tool.pip import Pip
from macaron.slsa_analyzer.build_tool.poetry import Poetry
from macaron.slsa_analyzer.checks.build_as_code_check import BuildAsCodeCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.github_actions import GHWorkflowType, GitHubActions, GitHubNode
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.specs.ci_spec import CIInfo


def test_build_as_code_check(
    maven_tool: Maven,
    gradle_tool: Gradle,
    poetry_tool: Poetry,
    pip_tool: Pip,
    github_actions_service: GitHubActions,
    jenkins_service: Jenkins,
    travis_service: Travis,
    circle_ci_service: CircleCI,
    gitlab_ci_service: GitLabCI,
) -> None:
    """Test the Build As Code Check."""
    check = BuildAsCodeCheck()
    check_result = CheckResult(justification=[])  # type: ignore
    bash_commands = BashCommands(caller_path="source_file", CI_path="ci_file", CI_type="github_actions", commands=[[]])
    ci_info = CIInfo(
        service=github_actions_service,
        bash_commands=[bash_commands],
        callgraph=CallGraph(BaseNode(), ""),
        provenance_assets=[],
        latest_release={},
        provenances=[],
    )

    # The target repo uses Maven build tool but does not deploy artifacts.
    use_build_tool = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    use_build_tool.dynamic_data["build_spec"]["tool"] = maven_tool
    assert check.run_check(use_build_tool, check_result) == CheckResultType.FAILED

    # The target repo uses Gradle build tool but does not deploy artifacts.
    use_build_tool = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    use_build_tool.dynamic_data["build_spec"]["tool"] = gradle_tool
    assert check.run_check(use_build_tool, check_result) == CheckResultType.FAILED

    # The target repo uses Poetry build tool but does not deploy artifacts.
    use_build_tool = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    use_build_tool.dynamic_data["build_spec"]["tool"] = poetry_tool
    assert check.run_check(use_build_tool, check_result) == CheckResultType.FAILED

    # The target repo uses Pip build tool but does not deploy artifacts.
    use_build_tool = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    use_build_tool.dynamic_data["build_spec"]["tool"] = pip_tool
    assert check.run_check(use_build_tool, check_result) == CheckResultType.FAILED

    # The target repo does not use a build tool.
    no_build_tool = AnalyzeContext("no_build_tool", os.path.abspath("./"), MagicMock())
    assert check.run_check(no_build_tool, check_result) == CheckResultType.FAILED

    # Use mvn deploy to deploy the artifact.
    maven_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    maven_deploy.dynamic_data["build_spec"]["tool"] = maven_tool
    bash_commands["commands"] = [["mvn", "deploy"]]
    maven_deploy.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(maven_deploy, check_result) == CheckResultType.PASSED

    # Use the mvn in the local directory to deploy the artifact.
    bash_commands["commands"] = [["./mvn", "deploy"]]
    maven_deploy.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(maven_deploy, check_result) == CheckResultType.PASSED

    # Use an invalid build command that has mvn.
    bash_commands["commands"] = [["mvnblah", "deploy"]]
    maven_deploy.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(maven_deploy, check_result) == CheckResultType.FAILED

    # Use mvn but do not deploy artifacts.
    no_maven_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    no_maven_deploy.dynamic_data["build_spec"]["tool"] = maven_tool
    bash_commands["commands"] = [["mvn", "verify"]]
    no_maven_deploy.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(no_maven_deploy, check_result) == CheckResultType.FAILED

    # Use an invalid goal that has deploy keyword.
    bash_commands["commands"] = [["mvnb", "deployblah"]]
    no_maven_deploy.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(no_maven_deploy, check_result) == CheckResultType.FAILED

    # Use gradle to deploy the artifact.
    gradle_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    gradle_deploy.dynamic_data["build_spec"]["tool"] = gradle_tool
    bash_commands["commands"] = [["./gradlew", "publishToSonatype"]]
    gradle_deploy.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(gradle_deploy, check_result) == CheckResultType.PASSED

    # Use poetry publish to publish the artifact.
    poetry_publish = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    poetry_publish.dynamic_data["build_spec"]["tool"] = poetry_tool
    bash_commands["commands"] = [["poetry", "publish"]]
    poetry_publish.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(poetry_publish, check_result) == CheckResultType.PASSED

    # Use Poetry but do not deploy artifacts.
    no_poetry_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    no_poetry_deploy.dynamic_data["build_spec"]["tool"] = poetry_tool
    bash_commands["commands"] = [["poetry", "upload"]]
    no_poetry_deploy.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(no_maven_deploy, check_result) == CheckResultType.FAILED

    # Use twine upload to deploy the artifact.
    twine_upload = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    twine_upload.dynamic_data["build_spec"]["tool"] = pip_tool
    bash_commands["commands"] = [["twine", "upload", "dist/*"]]
    twine_upload.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(twine_upload, check_result) == CheckResultType.PASSED

    # Use flit publish to deploy the artifact.
    flit_publish = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    flit_publish.dynamic_data["build_spec"]["tool"] = pip_tool
    bash_commands["commands"] = [["flit", "publish"]]
    flit_publish.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(flit_publish, check_result) == CheckResultType.PASSED

    # Test Jenkins.
    maven_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    maven_deploy.dynamic_data["build_spec"]["tool"] = maven_tool
    ci_info["service"] = jenkins_service
    bash_commands["commands"] = []
    maven_deploy.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(maven_deploy, check_result) == CheckResultType.FAILED

    # Test Travis.
    maven_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    maven_deploy.dynamic_data["build_spec"]["tool"] = maven_tool
    ci_info["service"] = travis_service
    bash_commands["commands"] = []
    maven_deploy.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(maven_deploy, check_result) == CheckResultType.FAILED

    # Test Circle CI.
    maven_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    maven_deploy.dynamic_data["build_spec"]["tool"] = maven_tool
    ci_info["service"] = circle_ci_service
    bash_commands["commands"] = []
    maven_deploy.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(maven_deploy, check_result) == CheckResultType.FAILED

    # Test GitLab CI.
    maven_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    maven_deploy.dynamic_data["build_spec"]["tool"] = maven_tool
    ci_info["service"] = gitlab_ci_service
    bash_commands["commands"] = []
    maven_deploy.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(maven_deploy, check_result) == CheckResultType.FAILED


def test_gha_workflow_deployment(
    pip_tool: Pip,
    github_actions_service: GitHubActions,
) -> None:
    """Test the use of verified GitHub Actions to deploy."""
    check = BuildAsCodeCheck()
    check_result = CheckResult(justification=[])  # type: ignore
    ci_info = CIInfo(
        service=github_actions_service,
        bash_commands=[],
        callgraph=CallGraph(BaseNode(), ""),
        provenance_assets=[],
        latest_release={},
        provenances=[],
    )

    workflows_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "github", "workflow_files")

    # This Github Actions workflow uses gh-action-pypi-publish to publish the artifact.
    gha_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
    gha_deploy.dynamic_data["build_spec"]["tool"] = pip_tool
    gha_deploy.dynamic_data["ci_services"] = [ci_info]

    root = GitHubNode(name="root", node_type=GHWorkflowType.NONE, source_path="", parsed_obj={}, caller_path="")
    gh_cg = CallGraph(root, "")
    workflow_path = os.path.join(workflows_dir, "pypi_publish.yaml")
    parsed_obj = parse_action(workflow_path, macaron_path=str(Path(macaron.MACARON_PATH)))
    callee = GitHubNode(
        name=os.path.basename(workflow_path),
        node_type=GHWorkflowType.INTERNAL,
        source_path=workflow_path,
        parsed_obj=parsed_obj,
        caller_path="",
    )
    root.add_callee(callee)
    github_actions_service.build_call_graph_from_node(callee)
    ci_info["callgraph"] = gh_cg
    assert check.run_check(gha_deploy, check_result) == CheckResultType.PASSED

    # This Github Actions workflow is not using a trusted action to publish the artifact.
    root = GitHubNode(name="root", node_type=GHWorkflowType.NONE, source_path="", parsed_obj={}, caller_path="")
    gh_cg = CallGraph(root, "")
    workflow_path = os.path.join(workflows_dir, "pypi_publish_blah.yaml")
    parsed_obj = parse_action(workflow_path, macaron_path=str(Path(macaron.MACARON_PATH)))
    callee = GitHubNode(
        name=os.path.basename(workflow_path),
        node_type=GHWorkflowType.INTERNAL,
        source_path=workflow_path,
        parsed_obj=parsed_obj,
        caller_path="",
    )
    root.add_callee(callee)
    github_actions_service.build_call_graph_from_node(callee)
    ci_info["callgraph"] = gh_cg
    assert check.run_check(gha_deploy, check_result) == CheckResultType.FAILED


@pytest.mark.parametrize(
    ("repo_path", "expect_result"),
    [
        (Path(__file__).parent.joinpath("resources", "build_as_code", "travis_ci_with_deploy"), CheckResultType.PASSED),
        (Path(__file__).parent.joinpath("resources", "build_as_code", "travis_ci_no_deploy"), CheckResultType.FAILED),
    ],
)
def test_travis_ci_deploy(
    gradle_tool: Gradle, travis_service: Jenkins, repo_path: Path, expect_result: CheckResultType
) -> None:
    """Test the Gradle build tool."""
    check = BuildAsCodeCheck()

    ci_info = CIInfo(
        service=travis_service,
        bash_commands=[],
        callgraph=CallGraph(BaseNode(), ""),
        provenance_assets=[],
        latest_release={},
        provenances=[],
    )
    check_result = CheckResult(justification=[])  # type: ignore
    gradle_deploy = AnalyzeContext("use_build_tool", str(repo_path.absolute()), MagicMock())
    gradle_deploy.dynamic_data["build_spec"]["tool"] = gradle_tool
    gradle_deploy.dynamic_data["ci_services"] = [ci_info]

    assert check.run_check(gradle_deploy, check_result) == expect_result
