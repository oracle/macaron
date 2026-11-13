# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Prove the workflow's assertions reject missing analysis and false pinning findings."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [
        ("passed", 0),
        ("unrelated", 0),
        ("unpinned", 1),
        ("invalid", 1),
        ("missing_check", 1),
        ("wrong_commit", 1),
        ("missing_policy", 1),
        ("wrong_outcome", 1),
    ],
)
def test_workflow_assertions(tmp_path: Path, mode: str, expected_code: int) -> None:
    """The same assertion program used in CI must fail for the original lockfile regression."""
    passed = mode in {"passed", "wrong_commit", "missing_check", "missing_policy", "wrong_outcome"}
    commit = "35ad4c011e7cfc84f7370397221f82823c74ce35" if mode != "wrong_commit" else "a" * 40
    purl = "pkg:github.com/graalvm/setup-graalvm@" + commit
    with closing(sqlite3.connect(tmp_path / "macaron.db")) as connection:
        connection.executescript("""
            CREATE TABLE component (id INTEGER, purl TEXT);
            CREATE TABLE repository (component_id INTEGER, full_name TEXT, commit_sha TEXT);
            CREATE TABLE check_result (id INTEGER, component_id INTEGER, check_id TEXT, passed INTEGER);
            CREATE TABLE check_facts (id INTEGER, component_id INTEGER, check_result_id INTEGER);
            CREATE TABLE github_actions_vulnerabilities_check
                (id INTEGER, finding_type TEXT, action_name TEXT, action_ref TEXT, caller_workflow TEXT);
        """)
        connection.execute("INSERT INTO component VALUES (1, ?)", (purl,))
        connection.execute("INSERT INTO repository VALUES (1, 'graalvm/setup-graalvm', ?)", (commit,))
        if mode != "missing_check":
            connection.execute(
                "INSERT INTO check_result VALUES (1, 1, 'mcn_githubactions_vulnerabilities_1', ?)", (int(passed),)
            )
        if not passed:
            finding = {
                "unrelated": "overbroad-permissions",
                "unpinned": "unpinned-third-party-action",
                "invalid": "invalid-actions-lockfile",
            }[mode]
            connection.execute("INSERT INTO check_facts VALUES (1, 1, 1)")
            connection.execute(
                "INSERT INTO github_actions_vulnerabilities_check VALUES (1, ?, ?, ?, ?)",
                (finding, "oracle/macaron", "v0.25.0", ".github/workflows/macaron-check-github-actions.yml"),
            )
        connection.commit()
    relation = "component_satisfies_policy" if passed else "component_violates_policy"
    report = {
        "passed_policies": [["github_actions_vulns"]] if passed else [],
        "failed_policies": [] if passed else [["github_actions_vulns"]],
        relation: [["1", purl, "github_actions_vulns"]],
    }
    if mode != "missing_policy":
        (tmp_path / "policy_report.json").write_text(json.dumps(report), encoding="utf-8")
    if passed:
        (tmp_path / "vsa.intoto.jsonl").write_text("{}\n", encoding="utf-8")
    script = (
        Path(__file__).resolve().parents[1]
        / "tutorial_resources/detect_vulnerable_github_actions/assert_lockfile_regression.py"
    )
    outcome = "failure" if not passed or mode == "wrong_outcome" else "success"
    result = subprocess.run(  # noqa: S603 - execute the checked-in assertion script with controlled test arguments.
        [sys.executable, str(script), str(tmp_path), outcome],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected_code, result.stdout + result.stderr
