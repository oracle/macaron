# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This modules contains tests for the provenance l3 check."""


from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.checks.provenance_l3_check import ProvenanceL3Check
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.github_actions import GitHubActions
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.git_service.api_client import GhAPIClient
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from tests.conftest import MockAnalyzeContext

from ...macaron_testcase import MacaronTestCase


class MockGitHubActions(GitHubActions):
    """Mock the GitHubActions class."""

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        return "run_feedback"


class MockGhAPIClient(GhAPIClient):
    """Mock GhAPIClient class."""

    def __init__(self, profile: dict):
        super().__init__(profile)
        self.release = {
            "assets": [
                {"name": "attestation.intoto.jsonl", "url": "URL", "size": "10"},
                {"name": "artifact.txt", "url": "URL", "size": "10"},
            ]
        }

    def get_latest_release(self, full_name: str) -> dict:
        return self.release

    def get_assets(self, release: dict, name: str = "", ext: str = "") -> list[dict]:
        return [item for item in self.release["assets"] if item["name"] == name or item["name"].endswith(ext)]

    def download_asset(self, url: str, download_path: str) -> bool:
        return True


class TestProvL3Check(MacaronTestCase):
    """Test the provenance l3 check."""

    def test_provenance_l3_check(self) -> None:
        """Test the provenance l3 check."""
        check = ProvenanceL3Check()
        check_result = CheckResult(justification=[])  # type: ignore
        github_actions = MockGitHubActions()
        api_client = MockGhAPIClient({"headers": {}, "query": []})
        github_actions.api_client = api_client
        github_actions.load_defaults()
        jenkins = Jenkins()
        jenkins.load_defaults()
        travis = Travis()
        travis.load_defaults()
        circle_ci = CircleCI()
        circle_ci.load_defaults()
        gitlab_ci = GitLabCI()
        gitlab_ci.load_defaults()

        ci_info = CIInfo(
            service=github_actions,
            bash_commands=[],
            callgraph=CallGraph(BaseNode(), ""),
            provenance_assets=[],
            latest_release={},
            provenances=[],
        )

        # Repo has provenances but no downloaded files.
        ci_info["provenance_assets"] = [{"name": "attestation.intoto.jsonl", "url": "URL", "size": "10"}]
        ci_info["latest_release"] = {
            "assets": [
                {"name": "attestation.intoto.jsonl", "url": "URL", "size": "10"},
                {"name": "artifact.txt", "url": "URL", "size": "10"},
            ]
        }
        ctx = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        ctx.dynamic_data["ci_services"] = [ci_info]
        assert check.run_check(ctx, check_result) == CheckResultType.FAILED

        # Attestation size is too large.
        ci_info["provenance_assets"] = [{"name": "attestation.intoto.jsonl", "url": "URL", "size": "100000000"}]
        ci_info["latest_release"] = {
            "assets": [
                {"name": "attestation.intoto.jsonl", "url": "URL", "size": "100000000"},
                {"name": "artifact.txt", "url": "URL", "size": "10"},
            ]
        }
        assert check.run_check(ctx, check_result) == CheckResultType.FAILED

        # No provenance available.
        ci_info["provenance_assets"] = []
        ci_info["latest_release"] = {
            "assets": [
                {"name": "attestation.intoto.jsonl", "url": "URL", "size": "10"},
                {"name": "artifact.txt", "url": "URL", "size": "10"},
            ]
        }
        assert check.run_check(ctx, check_result) == CheckResultType.FAILED

        # No release available
        ci_info["provenance_assets"] = [{"name": "attestation.intoto.jsonl", "url": "URL", "size": "10"}]
        ci_info["latest_release"] = {}
        assert check.run_check(ctx, check_result) == CheckResultType.FAILED

        # Test Jenkins.
        ci_info["service"] = jenkins
        assert check.run_check(ctx, check_result) == CheckResultType.FAILED

        # Test Travis.
        ci_info["service"] = travis
        assert check.run_check(ctx, check_result) == CheckResultType.FAILED

        # Test Circle CI.
        ci_info["service"] = circle_ci
        assert check.run_check(ctx, check_result) == CheckResultType.FAILED

        # Test GitLab CI.
        ci_info["service"] = gitlab_ci
        assert check.run_check(ctx, check_result) == CheckResultType.FAILED
