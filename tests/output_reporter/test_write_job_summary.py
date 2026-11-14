# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for GitHub Actions job summary rendering helpers."""

from __future__ import annotations

import importlib.util
import sqlite3
from contextlib import closing
from pathlib import Path
from types import ModuleType

import pytest


def _load_write_job_summary_module() -> ModuleType:
    """Load the write_job_summary script as a Python module for testing."""
    script_path = Path(Path(__file__).parents[2], "scripts", "actions", "write_job_summary.py")
    spec = importlib.util.spec_from_file_location("write_job_summary", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load write_job_summary.py module.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summary_preserves_locked_vulnerability_evidence(tmp_path: Path) -> None:
    """A locked vulnerable tag shows the effective commit and dependency chain."""
    module = _load_write_job_summary_module()
    summary = tmp_path / "summary.md"
    columns = [
        "finding_group",
        "finding_priority",
        "finding_type",
        "action_name",
        "action_ref",
        "vulnerable_workflow",
        "finding_message",
        "sha_pinned",
        "pinning_method",
        "resolved_commit",
        "lockfile_path",
        "dependency_chain",
    ]
    rows = [
        (
            "third_party_action_risk",
            100,
            "known-vulnerability",
            "example/child",
            "Main",
            "ci.yml",
            "Locked commit is vulnerable",
            0,
            "lockfile",
            "b" * 40,
            ".github/workflows/actions.lock",
            '["example/parent@v1", "example/child@Main"]',
        )
    ]
    assert module.write_compact_gha_vuln_diagnostics(summary, columns, rows) is True
    output = summary.read_text(encoding="utf-8")
    assert "b" * 40 in output
    assert "example/parent@v1" in output
    assert ".github/workflows/actions.lock" in output
    assert "recorded lockfile coverage" in output.lower()


def test_old_database_diagnostics_are_actionable(tmp_path: Path) -> None:
    """The extended SQL must not run against a pre-feature view and fail obscurely."""
    module = _load_write_job_summary_module()
    with closing(sqlite3.connect(tmp_path / "old.db")) as connection:
        connection.execute("CREATE TABLE github_actions_vulnerabilities_check (id INTEGER)")
        with pytest.raises(sqlite3.DatabaseError, match="fresh output directory"):
            module.validate_github_actions_schema(connection)


def test_workflow_security_table_includes_summary_column(tmp_path: Path) -> None:
    """Render workflow security findings with the short summary column in compact table output."""
    module = _load_write_job_summary_module()
    summary_path = Path(tmp_path, "summary.md")
    columns = [
        "finding_group",
        "finding_priority",
        "finding_type",
        "action_name",
        "action_ref",
        "vulnerable_workflow",
        "finding_message",
    ]
    rows = [
        (
            "workflow_security_issue",
            80,
            "remote-script-exec",
            "https://github.com/org/repo/.github/workflows/build.yml",
            "",
            "https://github.com/org/repo/.github/workflows/build.yml",
            (
                "Summary: Workflow downloads and executes remote scripts inline. "
                "Details: remote-script-exec: A step appears to download and pipe to shell (`curl|bash`). "
                "Recommendation: Avoid curl|bash patterns."
            ),
        ),
    ]

    rendered = module.write_compact_gha_vuln_diagnostics(summary_path, columns, rows)
    output = summary_path.read_text(encoding="utf-8")

    assert rendered is True
    assert "| priority | type | summary | workflow |" in output
    assert "Workflow downloads and executes remote scripts inline." in output


def test_compact_summary_keeps_all_groups_in_detailed_section(tmp_path: Path) -> None:
    """Render detailed section with both finding groups even when top priorities are workflow-only."""
    module = _load_write_job_summary_module()
    summary_path = Path(tmp_path, "summary.md")
    columns = [
        "finding_group",
        "finding_priority",
        "finding_type",
        "action_name",
        "action_ref",
        "vulnerable_workflow",
        "finding_message",
    ]
    rows = [
        (
            "workflow_security_issue",
            100,
            "potential-injection",
            "",
            "",
            "https://github.com/org/repo/.github/workflows/ci.yml",
            "Summary: Injection risk. Details: ... Recommendation: ...",
        ),
        (
            "third_party_action_risk",
            20,
            "unpinned-third-party-action",
            "actions/checkout",
            "v4",
            "https://github.com/org/repo/.github/workflows/ci.yml",
            "Summary: Unpinned action. Recommendation: ...",
        ),
    ]

    rendered = module.write_compact_gha_vuln_diagnostics(summary_path, columns, rows)
    output = summary_path.read_text(encoding="utf-8")

    assert rendered is True
    assert "#### Workflow security issues" in output
    assert "#### Third-party action risks" in output
    assert "**Workflow security issues**" in output
    assert "**Third-party action risks**" in output
    assert "`actions/checkout@v4`" in output
