# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Uv build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.uv import Uv
from tests.conftest import MockAnalyzeContext


@pytest.mark.parametrize(
    ("repo_files", "expected_value"),
    [
        (
            {
                "pyproject.toml": '[project]\nname = "sample"\nversion = "0.1.0"\n[tool.uv]\n',
                "uv.lock": "version = 1\n",
            },
            [("pyproject.toml", 1.0, None, None)],
        ),
        (
            {
                "pyproject.toml": (
                    '[build-system]\nrequires = ["uv_build>=0.9.5,<0.10.0"]\nbuild-backend = "uv_build"\n'
                ),
            },
            [("pyproject.toml", 1.0, None, None)],
        ),
        (
            {
                "pyproject.toml": (
                    '[build-system]\nrequires = ["pdm-backend>=2.4.0"]\nbuild-backend = "pdm.backend"\n'
                ),
            },
            [("pyproject.toml", 1.0, None, None)],
        ),
        (
            {
                "pyproject.toml": '[project]\nname = "sample"\nversion = "0.1.0"\n',
            },
            [],
        ),
    ],
)
def test_uv_build_tool_with_pyproject_detection(
    uv_tool: Uv,
    tmp_path: Path,
    repo_files: dict[str, str],
    expected_value: list[tuple[str, float, str | None, str | None]],
) -> None:
    """Test uv detection with lock file, tool section, and build-system metadata."""
    for relative_path, content in repo_files.items():
        path = tmp_path.joinpath(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    ctx = MockAnalyzeContext(macaron_path="", output_dir="", fs_path=str(tmp_path))
    assert uv_tool.is_detected(ctx.component) == expected_value
