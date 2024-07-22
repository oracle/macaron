# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This modules contains tests for the provenance available check."""


import os
import shutil
from pathlib import Path

import pytest

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.database.table_definitions import Repository
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.provenance_available_check import ProvenanceAvailableCheck
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.git_service.api_client import GhAPIClient
from macaron.slsa_analyzer.package_registry.npm_registry import NPMRegistry
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo
from tests.conftest import MockAnalyzeContext


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
                {"name": "attestation.intoto.jsonl", "url": "URL", "size": 10},
                {"name": "artifact.txt", "url": "URL", "size": 10},
            ]
        }

    def get_latest_release(self, full_name: str) -> dict:
        return self.release

    def download_asset(self, url: str, download_path: str) -> bool:
        return False


class MockNPMRegistry(NPMRegistry):
    """Mock NPMRegistry class."""

    resource_valid_prov_dir: str

    def download_package_json(self, url: str, download_path: str) -> bool:
        src_path = os.path.join(self.resource_valid_prov_dir, "sigstore-mock.payload.json")
        try:
            shutil.copy2(src_path, download_path)
        except shutil.Error:
            return False
        return True


@pytest.mark.parametrize(
    ("repository", "expected"),
    [
        (None, CheckResultType.FAILED),
        (Repository(complete_name="github.com/package-url/purl-spec", fs_path=""), CheckResultType.PASSED),
    ],
)
def test_provenance_available_check_with_repos(macaron_path: Path, repository: Repository, expected: str) -> None:
    """Test the provenance available check on different types of repositories."""
    check = ProvenanceAvailableCheck()
    github_actions = MockGitHubActions()
    api_client = MockGhAPIClient({"headers": {}, "query": []})
    github_actions.api_client = api_client
    github_actions.load_defaults()

    ci_info = CIInfo(
        service=github_actions,
        callgraph=CallGraph(BaseNode(), ""),
        provenance_assets=[],
        latest_release={},
        provenances=[],
    )

    # Set up the context object with provenances.
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.component.repository = repository
    ctx.dynamic_data["ci_services"] = [ci_info]
    assert check.run_check(ctx).result_type == expected


def test_provenance_available_check_on_ci(macaron_path: Path) -> None:
    """Test the provenance available check on different types of CI services."""
    check = ProvenanceAvailableCheck()
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
        callgraph=CallGraph(BaseNode(), ""),
        provenance_assets=[],
        latest_release={},
        provenances=[],
    )

    # Set up the context object with provenances.
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.dynamic_data["ci_services"] = [ci_info]

    # Repo doesn't have a provenance.
    api_client.release = {"assets": [{"name": "attestation.intoto", "url": "URL", "size": 10}]}
    assert check.run_check(ctx).result_type == CheckResultType.FAILED

    api_client.release = {"assets": [{"name": "attestation.intoto.jsonl", "url": "URL", "size": 10}]}

    # Test Jenkins.
    ci_info["service"] = jenkins
    assert check.run_check(ctx).result_type == CheckResultType.FAILED

    # Test Travis.
    ci_info["service"] = travis
    assert check.run_check(ctx).result_type == CheckResultType.FAILED

    # Test Circle CI.
    ci_info["service"] = circle_ci
    assert check.run_check(ctx).result_type == CheckResultType.FAILED

    # Test GitLab CI.
    ci_info["service"] = gitlab_ci
    assert check.run_check(ctx).result_type == CheckResultType.FAILED


@pytest.mark.parametrize(
    (
        "build_tool_name",
        "expected",
    ),
    [
        ("npm", CheckResultType.PASSED),
        ("yarn", CheckResultType.PASSED),
        ("go", CheckResultType.FAILED),
        ("maven", CheckResultType.FAILED),
    ],
)
def test_provenance_available_check_on_npm_registry(
    macaron_path: Path,
    test_dir: Path,
    build_tool_name: str,
    expected: CheckResultType,
    build_tools: dict[str, BaseBuildTool],
) -> None:
    """Test npm provenances published on npm registry."""
    check = ProvenanceAvailableCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.component.purl = "pkg:npm/@sigstore/mock@0.1.0"
    npm_registry = MockNPMRegistry()
    npm_registry.resource_valid_prov_dir = os.path.join(
        test_dir, "slsa_analyzer", "provenance", "resources", "valid_provenances"
    )
    npm_registry.load_defaults()
    ctx.dynamic_data["package_registries"] = [
        PackageRegistryInfo(
            build_tool=build_tools[build_tool_name],
            package_registry=npm_registry,
        )
    ]

    assert check.run_check(ctx).result_type == expected
