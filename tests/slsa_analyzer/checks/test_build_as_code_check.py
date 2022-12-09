# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Build As Code Check."""

import os
from unittest.mock import MagicMock

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.parsers.bashparser import BashCommands
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.checks.build_as_code_check import BuildAsCodeCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.github_actions import GitHubActions
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.specs.ci_spec import CIInfo

from ...macaron_testcase import MacaronTestCase


class MockGitHubActions(GitHubActions):
    """Mock the GitHubActions class."""

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        return "run_feedback"


class TestBuildAsCodeCheck(MacaronTestCase):
    """Test the Build as Code Check."""

    def test_build_as_code_check(self) -> None:
        """Test the Build As Code Check."""
        check = BuildAsCodeCheck()
        check_result = CheckResult(justification=[])  # type: ignore
        maven = Maven()
        maven.load_defaults()
        gradle = Gradle()
        gradle.load_defaults()
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
            caller_path="source_file", CI_path="ci_file", CI_type="github_actions", commands=[[]]
        )
        ci_info = CIInfo(
            service=github_actions,
            bash_commands=[bash_commands],
            callgraph=CallGraph(BaseNode(), ""),
            provenance_assets=[],
            latest_release={},
            provenances=[],
        )

        # The target repo uses Maven build tool but does not deploy artifacts.
        use_build_tool = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
        use_build_tool.dynamic_data["build_spec"]["tool"] = maven
        assert check.run_check(use_build_tool, check_result) == CheckResultType.FAILED

        # The target repo uses Gradle build tool but does not deploy artifacts.
        use_build_tool = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
        use_build_tool.dynamic_data["build_spec"]["tool"] = gradle
        assert check.run_check(use_build_tool, check_result) == CheckResultType.FAILED

        # The target repo does not use a build tool.
        no_build_tool = AnalyzeContext("no_build_tool", os.path.abspath("./"), MagicMock())
        assert check.run_check(no_build_tool, check_result) == CheckResultType.FAILED

        # Use mvn deploy to deploy the artifact.
        maven_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
        maven_deploy.dynamic_data["build_spec"]["tool"] = maven
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
        no_maven_deploy.dynamic_data["build_spec"]["tool"] = maven
        bash_commands["commands"] = [["mvn", "verify"]]
        no_maven_deploy.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(no_maven_deploy, check_result) == CheckResultType.FAILED

        # Use an invalid goal that has deploy keyword.
        bash_commands["commands"] = [["mvnb", "deployblah"]]
        no_maven_deploy.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(no_maven_deploy, check_result) == CheckResultType.FAILED

        # Use gradle to deploy the artifact.
        gradle_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
        gradle_deploy.dynamic_data["build_spec"]["tool"] = gradle
        bash_commands["commands"] = [["./gradlew", "publishToSonatype"]]
        gradle_deploy.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(gradle_deploy, check_result) == CheckResultType.PASSED

        # Test Jenkins.
        maven_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
        maven_deploy.dynamic_data["build_spec"]["tool"] = maven
        ci_info["service"] = jenkins
        bash_commands["commands"] = []
        maven_deploy.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_deploy, check_result) == CheckResultType.FAILED

        # Test Travis.
        maven_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
        maven_deploy.dynamic_data["build_spec"]["tool"] = maven
        ci_info["service"] = travis
        bash_commands["commands"] = []
        maven_deploy.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_deploy, check_result) == CheckResultType.FAILED

        # Test Circle CI.
        maven_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
        maven_deploy.dynamic_data["build_spec"]["tool"] = maven
        ci_info["service"] = circle_ci
        bash_commands["commands"] = []
        maven_deploy.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_deploy, check_result) == CheckResultType.FAILED

        # Test GitLab CI.
        maven_deploy = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
        maven_deploy.dynamic_data["build_spec"]["tool"] = maven
        ci_info["service"] = gitlab_ci
        bash_commands["commands"] = []
        maven_deploy.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(maven_deploy, check_result) == CheckResultType.FAILED
