# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the provenance finder."""
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from git import InvalidGitRepositoryError
from packageurl import PackageURL
from pydriller import Git

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.repo_finder.provenance_finder import find_gav_provenance, find_npm_provenance, find_provenance_from_ci
from macaron.slsa_analyzer.ci_service import BaseCIService, CircleCI, GitHubActions, GitLabCI, Jenkins, Travis
from macaron.slsa_analyzer.git_service.api_client import GhAPIClient
from macaron.slsa_analyzer.package_registry import JFrogMavenRegistry, NPMRegistry
from macaron.slsa_analyzer.package_registry.jfrog_maven_registry import JFrogMavenAsset, JFrogMavenAssetMetadata
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from macaron.slsa_analyzer.specs.inferred_provenance import Provenance
from tests.conftest import MockAnalyzeContext


class MockGitHubActions(GitHubActions):
    """Mock the GitHubActions class."""

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str | None, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        return "run_feedback"


class MockGhAPIClient(GhAPIClient):
    """Mock GhAPIClient class."""

    def __init__(self, profile: dict, resource_dir: str):
        super().__init__(profile)
        self.release = {
            "assets": [
                {"name": "attestation.intoto.jsonl", "url": "URL", "size": 10},
                {"name": "artifact.txt", "url": "URL", "size": 10},
            ]
        }
        self.resource_dir = resource_dir

    def get_release_by_tag(self, full_name: str, tag: str) -> dict | None:
        return self.release

    def download_asset(self, url: str, download_path: str) -> bool:
        target = os.path.join(
            self.resource_dir,
            "slsa_analyzer",
            "provenance",
            "resources",
            "valid_provenances",
            "slsa-verifier-linux-amd64.intoto.jsonl",
        )
        try:
            shutil.copy2(target, download_path)
        except shutil.Error:
            return False
        return True


class MockGit(Git):
    """Mock Pydriller.Git class."""

    def __init__(self) -> None:
        # To safely create a Mock Git object we let instantiation occur and fail on an empty temporary directory.
        try:
            with tempfile.TemporaryDirectory() as temp:
                super().__init__(temp)
        except InvalidGitRepositoryError:
            pass

    class MockTag:
        """Mock Tag class."""

        # Must match conftest.MockAnalyzeContext.Component.Repository.commit_sha.
        commit = "dig"

        def __str__(self) -> str:
            return self.commit

    repo = SimpleNamespace(tags=[MockTag()])


class MockJFrogRegistry(JFrogMavenRegistry):
    """Mock JFrogMavenRegistry class."""

    def __init__(self, resource_dir: str):
        self.resource_dir = resource_dir
        super().__init__()
        self.enabled = True

    def download_asset(self, url: str, dest: str) -> bool:
        target = os.path.join(self.resource_dir, "slsa_analyzer", "provenance", "resources", "micronaut.intoto.jsonl")
        try:
            shutil.copy2(target, dest)
        except shutil.Error:
            return False
        return True

    def fetch_assets(
        self,
        group_id: str,
        artifact_id: str,
        version: str,
        extensions: set[str] | None = None,
    ) -> list[JFrogMavenAsset]:
        return [
            JFrogMavenAsset(
                "micronaut.intoto.jsonl",
                "io.micronaut",
                "micronaut",
                "1.0.0",
                metadata=JFrogMavenAssetMetadata(
                    size_in_bytes=100,
                    sha256_digest="sha256",
                    download_uri="",
                ),
                jfrog_maven_registry=self,
            )
        ]


class MockNPMRegistry(NPMRegistry):
    """Mock NPMRegistry class."""

    resource_valid_prov_dir: str

    def download_attestation_payload(self, url: str, download_path: str) -> bool:
        src_path = os.path.join(self.resource_valid_prov_dir, "sigstore-mock.payload.json")
        try:
            shutil.copy2(src_path, download_path)
        except shutil.Error:
            return False
        return True


@pytest.mark.parametrize(
    "service",
    [
        Jenkins(),
        Travis(),
        CircleCI(),
        GitLabCI(),
    ],
)
def test_provenance_on_unsupported_ci(macaron_path: Path, service: BaseCIService) -> None:
    """Test the provenance finder on unsupported CI setups."""
    service.load_defaults()

    ci_info = CIInfo(
        service=service,
        callgraph=CallGraph(BaseNode(), ""),
        provenance_assets=[],
        release={},
        provenances=[],
        build_info_results=InTotoV01Payload(statement=Provenance().payload),
    )

    # Set up the context object with provenances.
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.dynamic_data["ci_services"] = [ci_info]

    provenance = find_provenance_from_ci(ctx, None)
    assert provenance is None


def test_provenance_on_supported_ci(macaron_path: Path, test_dir: Path) -> None:
    """Test the provenance finder on supported CI setups."""
    github_actions = MockGitHubActions()
    api_client = MockGhAPIClient({"headers": {}, "query": []}, str(test_dir))
    github_actions.api_client = api_client
    github_actions.load_defaults()

    ci_info = CIInfo(
        service=github_actions,
        callgraph=CallGraph(BaseNode(), ""),
        provenance_assets=[],
        release={},
        provenances=[],
        build_info_results=InTotoV01Payload(statement=Provenance().payload),
    )

    # Set up the context object with provenances.
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.dynamic_data["ci_services"] = [ci_info]

    # Test with a valid setup.
    git_obj = MockGit()
    provenance = find_provenance_from_ci(ctx, git_obj)
    assert provenance

    # Test with a repo that doesn't have any accepted provenance.
    api_client.release = {"assets": [{"name": "attestation.intoto", "url": "URL", "size": 10}]}
    provenance = find_provenance_from_ci(ctx, MockGit())
    assert provenance is None


def test_provenance_available_on_npm_registry(
    test_dir: Path,
) -> None:
    """Test provenance published on npm registry."""
    purl = PackageURL.from_string("pkg:npm/@sigstore/mock@0.1.0")
    npm_registry = MockNPMRegistry()
    npm_registry.resource_valid_prov_dir = os.path.join(
        test_dir, "slsa_analyzer", "provenance", "resources", "valid_provenances"
    )
    provenance = find_npm_provenance(purl, npm_registry)

    assert provenance


def test_provenance_available_on_jfrog_registry(
    test_dir: Path,
) -> None:
    """Test provenance published on jfrog registry."""
    purl = PackageURL.from_string("pkg:/maven/io.micronaut/micronaut-core@4.2.3")
    jfrog_registry = MockJFrogRegistry(str(test_dir))
    provenance = find_gav_provenance(purl, jfrog_registry)

    assert provenance
