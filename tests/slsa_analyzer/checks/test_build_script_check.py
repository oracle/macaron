# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Build Script Check."""

from pathlib import Path

from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.checks.build_script_check import BuildScriptCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from tests.conftest import MockAnalyzeContext


def test_build_script_check(
    macaron_path: Path,
    maven_tool: Maven,
) -> None:
    """Test the Build Script Check."""
    check = BuildScriptCheck()

    # The target repo uses a build tool.
    use_build_tool = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    use_build_tool.dynamic_data["build_spec"]["tools"] = [maven_tool]

    assert check.run_check(use_build_tool).result_type == CheckResultType.PASSED

    # The target repo does not use a build tool.
    no_build_tool = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    no_build_tool.dynamic_data["build_spec"]["tools"] = []

    assert check.run_check(no_build_tool).result_type == CheckResultType.FAILED
