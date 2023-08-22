# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This modules contains tests for the provenance available check."""

import os

from macaron.database.table_definitions import Analysis, Component, Repository
from macaron.slsa_analyzer.analyze_context import AnalyzeContext, ChecksOutputs
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.checks.vcs_check import VCSCheck
from macaron.slsa_analyzer.git_service.base_git_service import NoneGitService
from macaron.slsa_analyzer.slsa_req import SLSALevels
from macaron.slsa_analyzer.specs.build_spec import BuildSpec

from ...macaron_testcase import MacaronTestCase
from ..mock_git_utils import initiate_repo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.join(BASE_DIR, "mock_repos", "vcs_check_repo/sample_repo")


# pylint: disable=super-init-not-called
class MockAnalyzeContext(AnalyzeContext):
    """This class can be initiated without a git obj."""

    def __init__(self) -> None:
        # Make the VCS Check fails.
        self.component = Component(purl="pkg:invalid/invalid", analysis=Analysis(), repository=None)
        self.ctx_data: dict = {}
        self.slsa_level = SLSALevels.LEVEL0
        self.is_full_reach = False
        self.dynamic_data: ChecksOutputs = ChecksOutputs(
            git_service=NoneGitService(),
            build_spec=BuildSpec(tools=[]),
            ci_services=[],
            is_inferred_prov=True,
            expectation=None,
            package_registries=[],
        )
        self.wrapper_path = ""
        self.output_dir = ""


class TestVCSCheck(MacaronTestCase):
    """Test the vcs check."""

    def test_vcs_check(self) -> None:
        """Test the vcs check."""
        check = VCSCheck()
        initiate_repo(REPO_DIR)
        check_result = CheckResult(justification=[])  # type: ignore

        component = Component(
            purl="pkg:github/package-url/purl-spec@244fd47e07d1004f0aed9c",
            analysis=Analysis(),
            repository=Repository(complete_name="github.com/package-url/purl-spec"),
        )
        use_git_repo = AnalyzeContext(component=component, macaron_path=REPO_DIR, output_dir="")
        assert check.run_check(use_git_repo, check_result) == CheckResultType.PASSED

        no_git_repo = MockAnalyzeContext()
        assert check.run_check(no_git_repo, check_result) == CheckResultType.FAILED
