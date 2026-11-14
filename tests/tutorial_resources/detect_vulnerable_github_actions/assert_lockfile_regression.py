# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Assert the pinned GraalVM lockfile regression from actual composite-action outputs."""

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

TARGET_COMMIT = "35ad4c011e7cfc84f7370397221f82823c74ce35"
COVERED_REFS = {
    "check-dist.yml": {
        ("actions/checkout", "v7.0.1"),
        ("actions/setup-node", "v7.1.0"),
        ("actions/upload-artifact", "v7.0.2"),
    },
    "ci.yml": {("actions/checkout", "v7.0.1"), ("actions/setup-node", "v7.1.0")},
    "macaron-check-github-actions.yml": {("actions/checkout", "v7.0.1"), ("oracle/macaron", "v0.25.0")},
    "update-dependabot-dist.yml": {("actions/checkout", "v7.0.1"), ("actions/download-artifact", "v8.0.2")},
    "verify-lockfile.yml": {("actions/checkout", "v7.0.1")},
}


def assert_lockfile_regression(output_dir: Path, action_outcome: str) -> None:
    """Fail on missing analysis, false pinning findings, or inconsistent policy/action outcomes.

    Assertions deliberately allow unrelated security findings: this test checks
    lockfile recognition, not the future vulnerability status of a real project.
    SQLite is opened read-only so a missing database cannot become an empty one.
    """
    database = output_dir / "macaron.db"
    assert database.is_file(), "The action did not produce its analysis database"
    policy_path = output_dir / "policy_report.json"
    assert policy_path.is_file(), "The action did not produce its policy report"
    report: object = json.loads(policy_path.read_text(encoding="utf-8"))
    assert isinstance(report, dict), "Policy report must be a JSON object"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        targets = connection.execute("""
            SELECT component.id, component.purl, repository.commit_sha
            FROM component JOIN repository ON repository.component_id = component.id
            WHERE repository.full_name = 'graalvm/setup-graalvm'
        """).fetchall()
        assert len(targets) == 1, f"Expected one analyzed GraalVM target, found {targets!r}"
        component_id, purl, commit = targets[0]
        assert commit == TARGET_COMMIT, f"Analyzed unexpected commit {commit}"
        results = connection.execute(
            """
            SELECT id, passed FROM check_result
            WHERE component_id = ? AND check_id = 'mcn_githubactions_vulnerabilities_1'
        """,
            (component_id,),
        ).fetchall()
        assert len(results) == 1, "GitHub Actions check was missing or duplicated"
        check_id, passed = results[0]
        facts = connection.execute(
            """
            SELECT gha.finding_type, gha.action_name, gha.action_ref, gha.caller_workflow
            FROM github_actions_vulnerabilities_check AS gha
            JOIN check_facts ON check_facts.id = gha.id
            WHERE check_facts.component_id = ? AND check_facts.check_result_id = ?
        """,
            (component_id, check_id),
        ).fetchall()
    assert bool(passed) == (not facts), "Check was skipped, failed without diagnostics, or disagrees with its facts"
    for finding_type, action_name, action_ref, caller in facts:
        assert finding_type != "invalid-actions-lockfile", f"Supported target lockfile was rejected: {caller}"
        if finding_type == "unpinned-third-party-action":
            workflow = str(caller).split("#", 1)[0].rsplit("/", 1)[-1]
            assert (action_name, action_ref) not in COVERED_REFS.get(workflow, set()), (
                f"Lockfile-covered call was incorrectly flagged: {caller}: {action_name}@{action_ref}"
            )
    policy_relation = "component_satisfies_policy" if passed else "component_violates_policy"
    assert [str(component_id), purl, "github_actions_vulns"] in report.get(policy_relation, []), (
        "Policy did not apply to the target or disagrees with the check"
    )
    assert report.get("passed_policies") == ([["github_actions_vulns"]] if passed else [])
    assert report.get("failed_policies") == ([] if passed else [["github_actions_vulns"]])
    assert action_outcome == ("success" if passed else "failure"), "Action outcome disagrees with policy"
    assert (output_dir / "vsa.intoto.jsonl").is_file() == bool(passed), "VSA generation disagrees with policy"


if __name__ == "__main__":
    assert len(sys.argv) == 3, "Usage: assert_lockfile_regression.py OUTPUT_DIR ACTION_OUTCOME"
    assert_lockfile_regression(Path(sys.argv[1]).resolve(), sys.argv[2])
