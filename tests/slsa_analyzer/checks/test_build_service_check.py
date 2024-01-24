# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Build Service Check."""

from typing import cast

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.parsers.bashparser import BashCommands
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.build_tool.pip import Pip
from macaron.slsa_analyzer.build_tool.poetry import Poetry
from macaron.slsa_analyzer.checks.build_service_check import BuildServiceCheck, BuildServiceFacts
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.github_actions import GitHubActions
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from tests.conftest import MockAnalyzeContext

from ...macaron_testcase import MacaronTestCase


class MockGitHubActions(GitHubActions):
    """Mock the GitHubActions class."""

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str | None, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        return "run_feedback"


class TestBuildServiceCheck(MacaronTestCase):
    """Test the Build Service Check."""

    def test_build_service_check(self) -> None:
        """Test the Build Service Check."""
        check = BuildServiceCheck()
        maven = Maven()
        maven.load_defaults()
        gradle = Gradle()
        gradle.load_defaults()
        poetry = Poetry()
        poetry.load_defaults()
        pip = Pip()
        pip.load_defaults()
        github_actions = MockGitHubActions()
        github_actions.load_defaults()
        jenkins = Jenkins()
        jenkins.load_defaults()
        travis = Travis()
        travis.load_defaults()
        circle_ci = CircleCI()
        circle_ci.load_defaults()
        gitlab_ci = GitLabCI()
        gitlab_ci.load_defaults()

        bash_commands = BashCommands(
            caller_path="source_file",
            CI_path="ci_file",
            CI_type="github_actions",
            commands=[[]],
            job_name="job",
            step_name="step",
        )
        ci_info = CIInfo(
            service=github_actions,
            bash_commands=[bash_commands],
            callgraph=CallGraph(BaseNode(), ""),
            provenance_assets=[],
            latest_release={},
            provenances=[],
        )

        # The target repo uses Maven build tool but does not use a service.
        use_build_tool = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        use_build_tool.dynamic_data["build_spec"]["tools"] = [maven]
        assert check.run_check(use_build_tool).result_type == CheckResultType.FAILED

        # The target repo uses Gradle build tool but does not use a service.
        use_build_tool = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        use_build_tool.dynamic_data["build_spec"]["tools"] = [gradle]
        assert check.run_check(use_build_tool).result_type == CheckResultType.FAILED

        # The target repo uses Poetry build tool but does not use a service.
        use_build_tool = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        use_build_tool.dynamic_data["build_spec"]["tools"] = [poetry]
        assert check.run_check(use_build_tool).result_type == CheckResultType.FAILED

        # The target repo uses Pip build tool but does not use a service.
        use_build_tool = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        use_build_tool.dynamic_data["build_spec"]["tools"] = [pip]
        assert check.run_check(use_build_tool).result_type == CheckResultType.FAILED

        # The target repo does not use a build tool.
        no_build_tool = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        no_build_tool.dynamic_data["build_spec"]["tools"] = []
        assert check.run_check(no_build_tool).result_type == CheckResultType.FAILED

        # The target repo has multiple build tools, but does not use a service.
        use_build_tool = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        use_build_tool.dynamic_data["build_spec"]["tools"] = [maven, gradle]
        assert check.run_check(use_build_tool).result_type == CheckResultType.FAILED

        # Use mvn build args in CI to build the artifact.
        maven_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        maven_build_ci.dynamic_data["build_spec"]["tools"] = [maven]
        bash_commands["commands"] = [["mvn", "package"]]
        maven_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_build_ci).result_type == CheckResultType.PASSED

        # Use the mvn in CI in the local directory to build the artifact.
        bash_commands["commands"] = [["./mvn", "package"]]
        maven_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_build_ci).result_type == CheckResultType.PASSED

        # Use an invalid build command that has mvn.
        bash_commands["commands"] = [["mvnblah", "package"]]
        maven_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_build_ci).result_type == CheckResultType.FAILED

        # Use mvn but do not use CI to build artifacts.
        no_maven_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        no_maven_build_ci.dynamic_data["build_spec"]["tools"] = [maven]
        bash_commands["commands"] = [["mvn", "test"]]
        no_maven_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(no_maven_build_ci).result_type == CheckResultType.FAILED

        # Use an invalid goal that has build keyword.
        bash_commands["commands"] = [["mvn", "packageblah"]]
        no_maven_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(no_maven_build_ci).result_type == CheckResultType.FAILED

        # Use gradle in CI to build the artifact.
        gradle_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        gradle_build_ci.dynamic_data["build_spec"]["tools"] = [gradle]
        bash_commands["commands"] = [["./gradlew", "build"]]
        gradle_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(gradle_build_ci).result_type == CheckResultType.PASSED

        # Use poetry in CI to build the artifact.
        poetry_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        poetry_build_ci.dynamic_data["build_spec"]["tools"] = [poetry]
        bash_commands["commands"] = [["poetry", "build"]]
        poetry_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(poetry_build_ci).result_type == CheckResultType.PASSED

        # Use pip in CI to build the artifact.
        pip_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        pip_build_ci.dynamic_data["build_spec"]["tools"] = [pip]
        bash_commands["commands"] = [["pip", "install"]]
        pip_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(pip_build_ci).result_type == CheckResultType.PASSED

        # Use flit in CI to build the artifact.
        flit_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        flit_build_ci.dynamic_data["build_spec"]["tools"] = [pip]
        bash_commands["commands"] = [["flit", "build"]]
        flit_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(flit_build_ci).result_type == CheckResultType.PASSED

        # Use pip as a module in CI to build the artifact.
        pip_interpreter_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        pip_interpreter_build_ci.dynamic_data["build_spec"]["tools"] = [pip]
        bash_commands["commands"] = [["python", "-m", "pip", "install"]]
        pip_interpreter_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(pip_interpreter_build_ci).result_type == CheckResultType.PASSED

        # Use pip as a module incorrectly in CI to build the artifact.
        no_pip_interpreter_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        no_pip_interpreter_build_ci.dynamic_data["build_spec"]["tools"] = [pip]
        bash_commands["commands"] = [["python", "pip", "install"]]
        no_pip_interpreter_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(no_pip_interpreter_build_ci).result_type == CheckResultType.FAILED

        # Use pip as a module in CI with invalid goal to build the artifact.
        no_pip_interpreter_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        no_pip_interpreter_build_ci.dynamic_data["build_spec"]["tools"] = [pip]
        bash_commands["commands"] = [["python", "-m", "pip", "install-"]]
        no_pip_interpreter_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(no_pip_interpreter_build_ci).result_type == CheckResultType.FAILED

        # Maven and Gradle are both used in CI to build the artifact
        multi_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        multi_build_ci.dynamic_data["build_spec"]["tools"] = [gradle, maven]
        bash_commands["commands"] = [["./gradlew", "build"], ["mvn", "package"]]
        multi_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(multi_build_ci).result_type == CheckResultType.PASSED

        # Maven is used in CI to build the artifact, Gradle is not
        maven_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        maven_build_ci.dynamic_data["build_spec"]["tools"] = [gradle, maven]
        bash_commands["commands"] = [["mvn", "package"]]
        maven_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_build_ci).result_type == CheckResultType.PASSED

        # No build tools used
        none_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        none_build_ci.dynamic_data["build_spec"]["tools"] = []
        none_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(none_build_ci).result_type == CheckResultType.FAILED

        # Test Jenkins.
        maven_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        maven_build_ci.dynamic_data["build_spec"]["tools"] = [maven]
        bash_commands["commands"] = []
        ci_info["service"] = jenkins
        maven_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_build_ci).result_type == CheckResultType.FAILED

        # Test Travis.
        maven_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        maven_build_ci.dynamic_data["build_spec"]["tools"] = [maven]
        bash_commands["commands"] = []
        ci_info["service"] = travis
        maven_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_build_ci).result_type == CheckResultType.FAILED

        # Test Circle CI.
        maven_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        maven_build_ci.dynamic_data["build_spec"]["tools"] = [maven]
        bash_commands["commands"] = []
        ci_info["service"] = circle_ci
        maven_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_build_ci).result_type == CheckResultType.FAILED

        # Test GitLab CI.
        maven_build_ci = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        maven_build_ci.dynamic_data["build_spec"]["tools"] = [maven]
        bash_commands["commands"] = []
        ci_info["service"] = gitlab_ci
        maven_build_ci.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_build_ci).result_type == CheckResultType.FAILED

    def test_multibuild_facts_saved(self) -> None:
        """Test that facts for all build tools are saved in the results tables in multi-build tool scenarios."""
        check = BuildServiceCheck()
        maven = Maven()
        maven.load_defaults()
        gradle = Gradle()
        gradle.load_defaults()
        github_actions = MockGitHubActions()
        github_actions.load_defaults()

        bash_commands = BashCommands(
            caller_path="source_file",
            CI_path="ci_file",
            CI_type="github_actions",
            commands=[["./gradlew", "build"], ["mvn", "package"]],
            job_name="job",
            step_name="step",
        )
        ci_info = CIInfo(
            service=github_actions,
            bash_commands=[bash_commands],
            callgraph=CallGraph(BaseNode(), ""),
            provenance_assets=[],
            latest_release={},
            provenances=[],
        )

        multi_deploy = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        multi_deploy.dynamic_data["build_spec"]["tools"] = [gradle, maven]
        multi_deploy.dynamic_data["ci_services"] = [ci_info]
        check_result = check.run_check(multi_deploy)
        assert check_result.result_type == CheckResultType.PASSED
        # Check facts exist for both gradle and maven
        existing_facts = [cast(BuildServiceFacts, f).build_tool_name for f in check_result.result_tables]
        assert gradle.name in existing_facts
        assert maven.name in existing_facts
