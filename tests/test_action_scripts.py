# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Test argument forwarding by the composite action's shell scripts."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("repo_path", "package_url", "target_args"),
    [
        ("https://github.com/example/project", "", ["-rp", "https://github.com/example/project"]),
        ("", "pkg:maven/example/project@1.0", ["-purl", "pkg:maven/example/project@1.0"]),
        (
            "https://github.com/example/project",
            "pkg:maven/example/project@1.0",
            ["-rp", "https://github.com/example/project", "-purl", "pkg:maven/example/project@1.0"],
        ),
    ],
    ids=["repository", "package", "package-with-repository"],
)
def test_action_analysis_target_arguments(
    tmp_path: Path, repo_path: str, package_url: str, target_args: list[str]
) -> None:
    """Preserve both the artifact identity and repository override for SBOM analysis."""
    capture = tmp_path / "arguments"
    macaron = tmp_path / "fake-macaron"
    macaron.write_text('#!/usr/bin/env bash\nprintf \'%s\\0\' "$@" > "$CAPTURE_ARGS"\n', encoding="utf-8")
    macaron.chmod(0o755)
    script = Path(__file__).resolve().parents[1] / "scripts/actions/run_macaron_analysis.sh"

    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(script)],
        cwd=tmp_path,
        env={
            "PATH": os.defpath,
            "MACARON": str(macaron),
            "CAPTURE_ARGS": str(capture),
            "REPO_PATH": repo_path,
            "PACKAGE_URL": package_url,
            "OUTPUT_DIR": "analysis output",
            "DEPS_DEPTH": "1",
            "SBOM_PATH": "example sbom.json",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert capture.read_bytes().decode().split("\0")[:-1] == [
        "--output",
        "analysis output",
        "-lr",
        ".",
        "analyze",
        *target_args,
        "--deps-depth",
        "1",
        "--sbom-path",
        "example sbom.json",
    ]
