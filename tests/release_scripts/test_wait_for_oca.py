# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Test the optional OCA gate without making GitHub requests."""

# The subprocess runs a repository script with a controlled GitHub CLI.
# ruff: noqa: S603, S607

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "mode",
    ["not_required", "success", "pending", "existing_pr", "failure", "cancelled", "missing", "api_error"],
)
def test_wait_for_oca(tmp_path: Path, mode: str) -> None:
    """Skip an obsolete requirement, wait for a pending check, and stop on failure."""
    cli = tmp_path / "gh"
    cli.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
mode = os.environ["OCA_TEST_MODE"]
root = Path(os.environ["OCA_TEST_ROOT"])
with (root / "requests").open("a") as log:
    log.write(json.dumps(args) + "\n")
if mode == "api_error":
    sys.exit("GitHub API unavailable")
if args[0] == "api" and "/rules/branches/" in args[1]:
    print(json.dumps([] if mode == "not_required" else [{
        "type": "required_status_checks",
        "parameters": {"required_status_checks": [{"context": "oca/oracle"}]},
    }]))
elif args[:2] == ["pr", "list"]:
    print("https://github.com/example/project/pull/7" if mode == "existing_pr" else "")
elif args[:2] == ["pr", "create"]:
    if mode == "existing_pr":
        sys.exit("Existing PR must be reused")
    print("https://github.com/example/project/pull/7")
elif args[:2] == ["pr", "view"]:
    print("a" * 40)
elif args[0] == "api" and "/commits/" + "a" * 40 + "/check-runs?check_name=oca%2Foracle" in args[1]:
    polled = root / "polled"
    pending = mode == "pending" and not polled.exists()
    polled.touch()
    print(json.dumps({"check_runs": [] if mode == "missing" else [{
        "id": 1,
        "name": "oca/oracle",
        "app": {"slug": "oracle-contributor-agreement"},
        "status": "in_progress" if pending else "completed",
        "conclusion": mode if mode in {"failure", "cancelled"} else "success",
    }]}))
else:
    sys.exit(f"Unexpected request: {args}")
""",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    script = Path(__file__).resolve().parents[2] / "scripts/release_scripts/wait_for_oca.sh"
    result = subprocess.run(
        ["bash", str(script)],
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "GH_REPO": "example/project",
            "GH_TOKEN": "test-token",
            "TO_HEAD": "main",
            "FROM_BASE": "origin/release",
            "OCA_TEST_MODE": mode,
            "OCA_TEST_ROOT": str(tmp_path),
            "OCA_CHECK_TIMEOUT_SECONDS": "1",
            "OCA_CHECK_INTERVAL_SECONDS": "0",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) is (mode in {"not_required", "success", "pending", "existing_pr"}), result.stderr
    requests = (tmp_path / "requests").read_text(encoding="utf-8").splitlines()
    if mode == "not_required":
        assert len(requests) == 1, "No PR should be opened when OCA is no longer required"
    if mode == "pending":
        assert len([request for request in requests if "check-runs?" in request]) == 2
