# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains tests for the expectation check."""

import os

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.slsa_analyzer.asset import VirtualReleaseAsset
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.provenance_l3_content_check import ProvenanceL3ContentCheck
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.git_service.api_client import GhAPIClient
from macaron.slsa_analyzer.provenance.expectations.cue import CUEExpectation
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload
from macaron.slsa_analyzer.provenance.loader import load_provenance_payload
from macaron.slsa_analyzer.provenance.slsa import SLSAProvenanceData
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from macaron.slsa_analyzer.specs.inferred_provenance import Provenance
from tests.conftest import MockAnalyzeContext

from ...macaron_testcase import MacaronTestCase


class MockGitHubActions(GitHubActions):
    """Mock the GitHubActions class."""

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str | None, commit_sha: str, commit_date: str, workflow: str
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

    def download_asset(self, url: str, download_path: str) -> bool:
        return True


class TestProvenanceL3ContentCheck(MacaronTestCase):
    """Test the expectation check."""

    def test_expectation_check(self) -> None:
        """Test the expectation check."""
        check = ProvenanceL3ContentCheck()
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

        prov_dir = os.path.join(self.macaron_test_dir, "slsa_analyzer", "provenance", "resources", "valid_provenances")
        expectation_dir = os.path.join(
            self.macaron_test_dir, "slsa_analyzer", "provenance", "expectations", "cue", "resources"
        )
        ctx = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")

        # Test GitHub Actions.
        ci_info = CIInfo(
            service=github_actions,
            callgraph=CallGraph(BaseNode(), ""),
            provenance_assets=[],
            release={},
            provenances=[],
            build_info_results=InTotoV01Payload(statement=Provenance().payload),
        )
        ctx.dynamic_data["ci_services"] = [ci_info]

        # Repo has inferred provenance and no expectation.
        ctx.dynamic_data["is_inferred_prov"] = True
        ctx.dynamic_data["expectation"] = None
        assert check.run_check(ctx).result_type == CheckResultType.UNKNOWN

        # Repo has a provenance, but no expectation.
        ci_info["provenances"] = [
            SLSAProvenanceData(
                asset=VirtualReleaseAsset(name="No_ASSET", url="NO_URL", size_in_bytes=0),
                payload=load_provenance_payload(os.path.join(prov_dir, "slsa-verifier-linux-amd64.intoto.jsonl")),
            ),
        ]
        ctx.dynamic_data["is_inferred_prov"] = False
        ctx.dynamic_data["expectation"] = None
        assert check.run_check(ctx).result_type == CheckResultType.UNKNOWN

        # Repo has a provenance but invalid expectation.
        ctx.dynamic_data["expectation"] = CUEExpectation.make_expectation(
            os.path.join(expectation_dir, "invalid_expectations", "invalid.cue")
        )
        assert check.run_check(ctx).result_type == CheckResultType.UNKNOWN

        # Repo has a provenance and valid expectation, but expectation fails.
        ctx.dynamic_data["expectation"] = CUEExpectation.make_expectation(
            os.path.join(expectation_dir, "valid_expectations", "slsa_verifier_FAIL.cue")
        )
        assert check.run_check(ctx).result_type == CheckResultType.FAILED

        # Repo has a provenance and valid expectation, and expectation passes.
        ctx.dynamic_data["expectation"] = CUEExpectation.make_expectation(
            os.path.join(expectation_dir, "valid_expectations", "slsa_verifier_PASS.cue")
        )
        assert check.run_check(ctx).result_type == CheckResultType.PASSED

        # Test Jenkins.
        ci_info["service"] = jenkins
        assert check.run_check(ctx).result_type == CheckResultType.PASSED

        # Test Travis.
        ci_info["service"] = travis
        assert check.run_check(ctx).result_type == CheckResultType.PASSED

        # Test Circle CI.
        ci_info["service"] = circle_ci
        assert check.run_check(ctx).result_type == CheckResultType.PASSED

        # Test GitLab CI.
        ci_info["service"] = gitlab_ci
        assert check.run_check(ctx).result_type == CheckResultType.PASSED

        # Repo has a (gzipped) provenance and valid expectation, and expectation passes.
        ci_info["service"] = github_actions
        ci_info["provenances"] = [
            SLSAProvenanceData(
                asset=VirtualReleaseAsset(name="No_ASSET", url="NO_URL", size_in_bytes=0),
                payload=load_provenance_payload(os.path.join(prov_dir, "slsa-verifier-linux-amd64.intoto.jsonl.gz")),
            )
        ]
        ctx.dynamic_data["expectation"] = CUEExpectation.make_expectation(
            os.path.join(expectation_dir, "valid_expectations", "slsa_verifier_PASS.cue")
        )
        assert check.run_check(ctx).result_type == CheckResultType.PASSED

        # Repo has a (gzipped) provenance and valid expectation, but expectation fails.
        ctx.dynamic_data["expectation"] = CUEExpectation.make_expectation(
            os.path.join(expectation_dir, "valid_expectations", "slsa_verifier_FAIL.cue")
        )
        assert check.run_check(ctx).result_type == CheckResultType.FAILED
