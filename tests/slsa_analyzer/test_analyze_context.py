# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains tests for the AnalyzeContext module."""

from unittest import TestCase
from unittest.mock import MagicMock

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.json_tools import JsonType
from macaron.slsa_analyzer.asset import VirtualReleaseAsset
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload, validate_intoto_payload
from macaron.slsa_analyzer.provenance.slsa import SLSAProvenanceData
from macaron.slsa_analyzer.slsa_req import ReqName, SLSAReqStatus
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from macaron.slsa_analyzer.specs.inferred_provenance import Provenance
from tests.conftest import MockAnalyzeContext


class TestAnalyzeContext(TestCase):
    """
    This class tests the AnalyzeContext module
    """

    MOCK_CTX_DATA = {
        ReqName.BUILD_SERVICE: SLSAReqStatus(),
        ReqName.VCS: SLSAReqStatus(),
    }

    MOCK_GIT_OBJ = MagicMock()

    MOCK_REPO_PATH = "/home/repo_name"

    MOCK_COMMIT_HASH = "6dcb09b5b57875f334f61aebed695e2e4193db5e"

    MOCK_DATE = "2021-04-5"

    def setUp(self) -> None:
        """
        Set up the sample AnalyzeContext instance
        """
        self.analyze_ctx = MockAnalyzeContext(macaron_path="", output_dir="")
        self.analyze_ctx.component.repository.full_name = "owner/repo_name"
        self.analyze_ctx.component.repository.fs_path = self.MOCK_REPO_PATH
        self.analyze_ctx.component.repository.commit_sha = self.MOCK_COMMIT_HASH
        self.analyze_ctx.component.repository.commit_date = self.MOCK_DATE
        self.analyze_ctx.ctx_data = self.MOCK_CTX_DATA

    def test_update_req_status(self) -> None:
        """
        Test updating one requirement in the context
        """
        self.analyze_ctx.update_req_status(ReqName.BUILD_SERVICE, True, "sample_fb")
        assert self.analyze_ctx.ctx_data[ReqName.BUILD_SERVICE].get_tuple() == (
            True,
            True,
            "sample_fb",
        )
        assert self.analyze_ctx.ctx_data[ReqName.VCS].get_tuple() != (
            True,
            True,
            "sample_fb",
        )

        self.analyze_ctx.update_req_status(ReqName.SCRIPTED_BUILD, True, "sample_fb")
        assert self.analyze_ctx.ctx_data == self.MOCK_CTX_DATA

        self.analyze_ctx.bulk_update_req_status([ReqName.BUILD_SERVICE, ReqName.VCS], False, "bulk_update")
        assert self.analyze_ctx.ctx_data[ReqName.BUILD_SERVICE].get_tuple() == (
            True,
            False,
            "bulk_update",
        )
        assert self.analyze_ctx.ctx_data[ReqName.VCS].get_tuple() == (
            True,
            False,
            "bulk_update",
        )

    def test_provenances(self) -> None:
        """Test getting the provenances data from an AnalyzeContext instance."""
        expected_provenance: dict[str, JsonType] = {
            "_type": "https://in-toto.io/Statement/v0.1",
            "subject": [],
            "predicateType": "https://slsa.dev/provenance/v0.2",
            "predicate": {},
        }

        expected_payload = validate_intoto_payload(expected_provenance)

        gh_actions = GitHubActions()

        gh_actions_ci_info = CIInfo(
            service=gh_actions,
            callgraph=CallGraph(BaseNode(), ""),
            provenance_assets=[],
            release={},
            provenances=[
                SLSAProvenanceData(
                    payload=expected_payload, asset=VirtualReleaseAsset(name="No_ASSET", url="NO_URL", size_in_bytes=0)
                ),
            ],
            build_info_results=InTotoV01Payload(statement=Provenance().payload),
        )

        self.analyze_ctx.dynamic_data["ci_services"].append(gh_actions_ci_info)
        result_provenance: dict = self.analyze_ctx.provenances.get(gh_actions.name)[0]  # type: ignore
        assert len(expected_provenance.keys()) == len(result_provenance.keys())
        for key, value in expected_provenance.items():
            assert result_provenance[key] == value

    def test_is_inferred_provenance(self) -> None:
        """Test the is_inferred_provenance property."""
        self.analyze_ctx.dynamic_data["is_inferred_prov"] = True
        assert self.analyze_ctx.is_inferred_provenance

        self.analyze_ctx.dynamic_data["is_inferred_prov"] = False
        assert not self.analyze_ctx.is_inferred_provenance
