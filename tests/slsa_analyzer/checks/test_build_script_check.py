# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Build Script Check."""

from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.checks.build_script_check import BuildScriptCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from tests.conftest import MockAnalyzeContext

from ...macaron_testcase import MacaronTestCase


class TestBuildScriptCheck(MacaronTestCase):
    """Test the Build Script Check."""

    def test_build_script_check(self) -> None:
        """Test the Build Script Check."""
        check = BuildScriptCheck()
        check_result = CheckResult(justification=[], result_tables=[])  # type: ignore
        maven = Maven()
        maven.load_defaults()

        # The target repo uses a build tool.
        use_build_tool = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        use_build_tool.dynamic_data["build_spec"]["tools"] = [maven]

        assert check.run_check(use_build_tool, check_result) == CheckResultType.PASSED

        # The target repo does not use a build tool.
        no_build_tool = MockAnalyzeContext(macaron_path=MacaronTestCase.macaron_path, output_dir="")
        no_build_tool.dynamic_data["build_spec"]["tools"] = []

        assert check.run_check(no_build_tool, check_result) == CheckResultType.FAILED
