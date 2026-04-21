# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Pip build functions."""

from pathlib import Path

import pytest

from macaron.slsa_analyzer.build_tool.pip import Pip
from tests.conftest import MockAnalyzeContext


@pytest.mark.parametrize(
    ("build_configs", "repo_files", "expected_value"),
    [
        (
            ["setup.py", "pyproject.toml", "setup.cfg"],
            {
                "setup.py": "",
                "pyproject.toml": "",
            },
            [
                ("pyproject.toml", 1.0, None, None),
                ("setup.py", 0.5, None, None),
            ],
        ),
        (
            ["setup.py", "setup.cfg"],
            {
                "setup.py": "",
                "setup.cfg": "",
            },
            [
                ("setup.py", 1.0, None, None),
                ("setup.cfg", 0.5, None, None),
            ],
        ),
        (
            ["setup.py", "setup.cfg", "pyproject.toml"],
            {
                "setup.py": "",
                "setup.cfg": "",
                "pyproject.toml": '[build-system]\nrequires = ["pdm-backend>=2.4.0"]\nbuild-backend = "pdm.backend"\n',
            },
            [
                ("pyproject.toml", 0.5, None, None),
                ("setup.py", 0.5, None, None),
                ("setup.cfg", 0.5, None, None),
            ],
        ),
    ],
)
def test_pip_build_tool_detection(
    pip_tool: Pip,
    tmp_path: Path,
    build_configs: list[str],
    repo_files: dict[str, str],
    expected_value: list[tuple[str, float, str | None, str | None]],
) -> None:
    """Test pyproject prioritization and confidence scoring across config combinations."""
    pip_tool.build_configs = build_configs
    for relative_path, content in repo_files.items():
        path = tmp_path.joinpath(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    ctx = MockAnalyzeContext(macaron_path="", output_dir="", fs_path=str(tmp_path))
    assert pip_tool.is_detected(ctx.component) == expected_value
