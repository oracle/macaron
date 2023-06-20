# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Build Script Check."""

import os
from unittest.mock import MagicMock

from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.checks.build_script_check import BuildScriptCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType

from ...macaron_testcase import MacaronTestCase


class TestBuildScriptCheck(MacaronTestCase):
    """Test the Build Script Check."""

    def test_build_script_check(self) -> None:
        """Test the Build Script Check."""
        check = BuildScriptCheck()
        check_result = CheckResult(justification=[], result_tables=[])  # type: ignore
        maven = Maven()
        gradle = Gradle()
        maven.load_defaults()

        # The target repo uses a build tool.
        use_build_tool = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
        use_build_tool.dynamic_data["build_spec"]["tools"] = [maven]

        assert check.run_check(use_build_tool, check_result) == CheckResultType.PASSED

        # The target repo uses multiple build tools
        use_build_tool = AnalyzeContext("use_build_tool", os.path.abspath("./"), MagicMock())
        use_build_tool.dynamic_data["build_spec"]["tools"] = [maven, gradle]

        assert check.run_check(use_build_tool, check_result) == CheckResultType.PASSED

        # The target repo does not use a build tool.
        no_build_tool = AnalyzeContext("no_build_tool", os.path.abspath("./"), MagicMock())

        assert check.run_check(no_build_tool, check_result) == CheckResultType.FAILED
