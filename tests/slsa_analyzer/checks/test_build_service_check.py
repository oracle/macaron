# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Build Service Check."""

from pathlib import Path
from typing import cast

import pytest

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.checks.build_service_check import BuildServiceCheck, BuildServiceFacts
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions
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
def test_build_service_check_no_callgraph(
    macaron_path: Path,
    build_tools: dict[str, BaseBuildTool],
    build_tool_name: str,
    ci_services: dict[str, BaseCIService],
    ci_name: str,
    expected_result: CheckResultType,
) -> None:
    """Test the Build Service Check when no callgraph is built for the CI service."""
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

    check = BuildServiceCheck()
    assert check.run_check(use_build_tool).result_type == expected_result


def test_no_build_tool(macaron_path: Path) -> None:
    """Test the Build As Code Check when no build tools are found."""
    check = BuildServiceCheck()
    no_build_tool = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    no_build_tool.dynamic_data["build_spec"]["tools"] = []
    assert check.run_check(no_build_tool).result_type == CheckResultType.FAILED


@pytest.mark.parametrize(
    ("build_tool_names", "commands", "expected_result"),
    [
        (["maven"], ["mvn package"], CheckResultType.PASSED),
        (["maven"], ["./mvn package"], CheckResultType.PASSED),
        (["maven"], ["mvnblah package"], CheckResultType.FAILED),
        (["maven"], ["mvn test"], CheckResultType.FAILED),
        (["maven"], ["mvn packageblah"], CheckResultType.FAILED),
        (["gradle"], ["./gradlew build"], CheckResultType.PASSED),
        (["poetry"], ["poetry build"], CheckResultType.PASSED),
        (["poetry"], ["pip install"], CheckResultType.FAILED),
        (["maven", "gradle"], ["./gradlew build", "mvn package"], CheckResultType.PASSED),
        (["maven", "gradle"], ["mvn package"], CheckResultType.PASSED),
        (["maven", "gradle"], [], CheckResultType.FAILED),
    ],
)
def test_packaging_commands(
    macaron_path: Path,
    build_tools: dict[str, BaseBuildTool],
    github_actions_service: GitHubActions,
    build_tool_names: str,
    commands: list[str],
    expected_result: CheckResultType,
) -> None:
    """Test the Build Service Check when with different build commands."""
    package_ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    package_ctx.dynamic_data["build_spec"]["tools"] = [build_tools[name] for name in build_tool_names]
    ci_info = CIInfo(
        service=github_actions_service,
        callgraph=build_github_actions_call_graph_for_commands(commands=commands),
        provenance_assets=[],
        release={},
        provenances=[],
        build_info_results=InTotoV01Payload(statement=Provenance().payload),
    )
    ci_info["service"] = github_actions_service
    package_ctx.dynamic_data["ci_services"] = [ci_info]
    check = BuildServiceCheck()
    assert check.run_check(package_ctx).result_type == expected_result


def test_multibuild_facts_saved(
    macaron_path: str, maven_tool: BaseBuildTool, gradle_tool: BaseBuildTool, github_actions_service: BaseCIService
) -> None:
    """Test that facts for all build tools are saved in the results tables in multi-build tool scenarios."""
    check = BuildServiceCheck()
    ci_info = CIInfo(
        service=github_actions_service,
        callgraph=build_github_actions_call_graph_for_commands(["./gradlew build", "mvn package"]),
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
    existing_facts = [cast(BuildServiceFacts, f).build_tool_name for f in check_result.result_tables]
    assert gradle_tool.name in existing_facts
    assert maven_tool.name in existing_facts
