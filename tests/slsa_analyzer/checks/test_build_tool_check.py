# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the build tool detection Check."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from tests.conftest import MockAnalyzeContext


@pytest.mark.parametrize(
    "build_tool_name",
    [
        "maven",
        "gradle",
        "poetry",
        "pip",
        "npm",
        "docker",
        "go",
    ],
)
def test_build_tool_check_pass(
    macaron_path: Path,
    build_tools: dict[str, BaseBuildTool],
    build_tool_name: str,
) -> None:
    """Test the build tool detection check passes."""
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.dynamic_data["build_spec"]["tools"] = [build_tools[build_tool_name]]
    check = BuildToolCheck()
    assert check.run_check(ctx).result_type == CheckResultType.PASSED


def test_build_tool_check_fail(
    macaron_path: Path,
) -> None:
    """Test the build tool detection check fails."""
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.dynamic_data["build_spec"]["tools"] = []
    check = BuildToolCheck()
    assert check.run_check(ctx).result_type == CheckResultType.FAILED
