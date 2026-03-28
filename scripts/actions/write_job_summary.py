#!/usr/bin/env python3

# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Generate GitHub Actions job summary content for Macaron action runs."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

CHECK_RESULT_DEFAULT_COLUMNS = ["id", "check_id", "passed", "component_id"]
EXISTING_POLICY_TABLE_COLUMNS: dict[str, dict[str, list[str]]] = {
    "check-github-actions": {
        "check_result": CHECK_RESULT_DEFAULT_COLUMNS,
        "github_actions_vulnerabilities_check": [
            "id",
            "github_actions_id",
            "github_actions_version",
            "caller_workflow",
            "vulnerability_urls",
        ],
    }
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _append_line(summary_path: Path, line: str = "") -> None:
    with summary_path.open("a", encoding="utf-8") as summary:
        summary.write(f"{line}\n")


def _resolve_policy_source(policy_input: str) -> tuple[Path | None, str]:
    """Resolve a policy input to either a local file or a predefined policy template path."""
    if not policy_input:
        return None, ""

    candidate = Path(policy_input)
    if candidate.is_file():
        return candidate, "file"

    action_path = _env("GITHUB_ACTION_PATH", "")
    if action_path:
        template_path = (
            Path(action_path)
            / "src"
            / "macaron"
            / "resources"
            / "policies"
            / "datalog"
            / (f"{policy_input}.dl.template")
        )
        if template_path.is_file():
            return template_path, "predefined"

    return None, "unresolved"


def _write_header(summary_path: Path, db_path: Path, policy_report: str, policy_file: str, html_report: str) -> None:
    reports_artifact_name = _env("REPORTS_ARTIFACT_NAME", "macaron-reports")
    run_url = (
        f"{_env('GITHUB_SERVER_URL', 'https://github.com')}/"
        f"{_env('GITHUB_REPOSITORY')}/actions/runs/{_env('GITHUB_RUN_ID')}"
    )
    reports_artifact_url = _env("REPORTS_ARTIFACT_URL", run_url)
    vsa_path = _env("VSA_PATH", "output/vsa.intoto.jsonl")
    policy_succeeded = bool(vsa_path) and Path(vsa_path).is_file()

    _append_line(summary_path, "## Macaron Analysis Results")
    _append_line(summary_path)
    _append_line(summary_path, "Download reports from this artifact link:")
    _append_line(summary_path, f"- [`{reports_artifact_name}`]({reports_artifact_url})")
    _append_line(summary_path)
    _append_line(summary_path, "Generated files:")
    if html_report:
        _append_line(summary_path, f"- HTML report: `{html_report}`")
    _append_line(summary_path, f"- Database: `{db_path}`")
    _append_line(summary_path, f"- Policy report: `{policy_report}`")
    if policy_file:
        _append_line(summary_path, f"- Policy file: `{policy_file}`")
    if policy_succeeded:
        _append_line(summary_path, "- Policy status: :white_check_mark: Policy verification succeeded.")
    else:
        _append_line(summary_path, "- Policy status: :x: Policy verification failed.")
    _append_line(summary_path)


def _write_vulnerability_table(summary_path: Path, db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT github_actions_id, github_actions_version, vulnerability_urls, caller_workflow
            FROM github_actions_vulnerabilities_check
            ORDER BY id
            """)
        rows = cur.fetchall()

    if not rows:
        _append_line(summary_path, ":white_check_mark: No vulnerable GitHub Actions detected.")
        return

    _append_line(summary_path, "| Action | Version | Vulnerabilities | Workflow |")
    _append_line(summary_path, "|---|---|---|---|")
    for action_id, version, vulnerability_urls, caller_workflow in rows:
        vuln_value = vulnerability_urls
        try:
            parsed = json.loads(vulnerability_urls)
            if isinstance(parsed, list):
                vuln_value = ", ".join(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
        _append_line(summary_path, f"| `{action_id}` | `{version}` | `{vuln_value}` | {caller_workflow} |")


def _parse_policy_checks(policy_file: Path) -> tuple[list[str], list[str]]:
    policy_text = policy_file.read_text(encoding="utf-8")
    check_relations = sorted(set(re.findall(r"\b(check_[A-Za-z0-9_]+)\s*\(", policy_text)))
    policy_check_ids = sorted(set(re.findall(r'"(mcn_[a-zA-Z0-9_]+)"', policy_text)))
    return check_relations, policy_check_ids


def _resolve_existing_table(conn: sqlite3.Connection, table_name: str) -> str | None:
    """Resolve a logical table name to an existing SQLite table name."""
    candidates = [table_name]
    if not table_name.startswith("_"):
        candidates.append(f"_{table_name}")

    cur = conn.cursor()
    for candidate in candidates:
        cur.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ? LIMIT 1", (candidate,))
        if cur.fetchone():
            return candidate
    return None


def _get_existing_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cur.fetchall()]


def _query_selected_columns(
    conn: sqlite3.Connection,
    table_name: str,
    desired_columns: list[str],
    where_clause: str = "",
    params: tuple[object, ...] = (),
) -> tuple[list[str], list[tuple]]:
    available = _get_existing_columns(conn, table_name)
    selected = [c for c in desired_columns if c in available]
    if not selected:
        return [], []

    sql = f"SELECT {', '.join(selected)} FROM {table_name}"
    if where_clause:
        sql = f"{sql} WHERE {where_clause}"
    sql = f"{sql} ORDER BY 1"
    cur = conn.cursor()
    cur.execute(sql, params)
    return selected, cur.fetchall()


def _write_markdown_table(summary_path: Path, columns: list[str], rows: list[tuple]) -> bool:
    if not columns or not rows:
        return False

    _append_line(summary_path, f"| {' | '.join(columns)} |")
    _append_line(summary_path, f"|{'|'.join(['---'] * len(columns))}|")
    for row in rows:
        values = [f"`{value}`" for value in row]
        _append_line(summary_path, f"| {' | '.join(values)} |")
    return True


def _write_policy_check_lists(summary_path: Path, check_relations: list[str], policy_check_ids: list[str]) -> None:
    if check_relations:
        _append_line(
            summary_path,
            f"- `check_*` relations in policy: {', '.join(f'`{name}`' for name in check_relations)}",
        )

    if policy_check_ids:
        _append_line(
            summary_path,
            f"- `mcn_*` checks referenced in policy: {', '.join(f'`{name}`' for name in policy_check_ids)}",
        )


def _write_custom_policy_failure_diagnostics(summary_path: Path, db_path: Path, policy_file: Path) -> None:
    check_relations, policy_check_ids = _parse_policy_checks(policy_file)
    has_details = False

    _append_line(summary_path)
    _append_line(summary_path, "### Policy Failure Diagnostics")
    _write_policy_check_lists(summary_path, check_relations, policy_check_ids)
    if check_relations or policy_check_ids:
        has_details = True

    if not policy_check_ids:
        if not has_details:
            _append_line(summary_path, "- Additional check-level details are unavailable for this failure.")
        return

    with sqlite3.connect(db_path) as conn:
        resolved = _resolve_existing_table(conn, "check_result")
        if not resolved:
            if not has_details:
                _append_line(summary_path, "- Additional check-level details are unavailable for this failure.")
            return
        placeholders = ",".join(["?"] * len(policy_check_ids))
        cols, rows = _query_selected_columns(
            conn,
            resolved,
            CHECK_RESULT_DEFAULT_COLUMNS,
            where_clause=f"check_id IN ({placeholders})",
            params=tuple(policy_check_ids),
        )

    _append_line(summary_path)
    _append_line(summary_path, "#### check_result")
    if _write_markdown_table(summary_path, cols, rows):
        has_details = True
    else:
        # Remove empty section header and provide a single friendly fallback below.
        _append_line(summary_path, "- Additional check-level details are unavailable for this failure.")


def _write_existing_policy_failure_diagnostics(
    summary_path: Path, db_path: Path, policy_name: str, policy_file: Path
) -> None:
    check_relations, policy_check_ids = _parse_policy_checks(policy_file)
    table_config = EXISTING_POLICY_TABLE_COLUMNS.get(policy_name, {"check_result": CHECK_RESULT_DEFAULT_COLUMNS})
    has_details = False

    _append_line(summary_path)
    _append_line(summary_path, f"### Policy Failure Diagnostics ({policy_name})")
    _write_policy_check_lists(summary_path, check_relations, policy_check_ids)
    if check_relations or policy_check_ids:
        has_details = True

    with sqlite3.connect(db_path) as conn:
        for logical_table, desired_columns in table_config.items():
            resolved = _resolve_existing_table(conn, logical_table)
            if not resolved:
                continue

            where_clause = ""
            params: tuple[object, ...] = ()
            if logical_table == "check_result" and policy_check_ids:
                placeholders = ",".join(["?"] * len(policy_check_ids))
                where_clause = f"check_id IN ({placeholders})"
                params = tuple(policy_check_ids)
            cols, rows = _query_selected_columns(conn, resolved, desired_columns, where_clause, params)
            if cols and rows:
                _append_line(summary_path)
                _append_line(summary_path, f"#### {logical_table}")
                if _write_markdown_table(summary_path, cols, rows):
                    has_details = True

    if not has_details:
        _append_line(summary_path, "- Additional check-level details are unavailable for this failure.")


def main() -> None:
    output_dir = Path(_env("OUTPUT_DIR", "output"))
    db_path = Path(_env("DB_PATH", str(output_dir / "macaron.db")))
    policy_report = _env("POLICY_REPORT", str(output_dir / "policy_report.json"))
    policy_file_value = _env("POLICY_FILE", "")
    resolved_policy_file, policy_mode = _resolve_policy_source(policy_file_value)
    policy_label = ""
    if policy_mode == "file" and resolved_policy_file:
        policy_label = str(resolved_policy_file)
    elif policy_mode == "predefined" and resolved_policy_file:
        policy_label = f"{policy_file_value} (predefined template: {resolved_policy_file})"
    elif policy_mode == "unresolved":
        policy_label = f"{policy_file_value} (unresolved)"
    html_report = _env("HTML_REPORT_PATH", "")
    vsa_path_value = _env("VSA_PATH", str(output_dir / "vsa.intoto.jsonl"))
    vsa_path = Path(vsa_path_value) if vsa_path_value else None

    summary_output = _env("GITHUB_STEP_SUMMARY")
    if not summary_output:
        raise RuntimeError("GITHUB_STEP_SUMMARY is not set.")
    summary_path = Path(summary_output)

    _write_header(summary_path, db_path, policy_report, policy_label, html_report)

    if not db_path.is_file():
        _append_line(summary_path, ":warning: Macaron database was not generated.")
        return

    _write_vulnerability_table(summary_path, db_path)

    if (not vsa_path or not vsa_path.is_file()) and resolved_policy_file and resolved_policy_file.is_file():
        if policy_mode == "predefined":
            _write_existing_policy_failure_diagnostics(summary_path, db_path, policy_file_value, resolved_policy_file)
        else:
            _write_custom_policy_failure_diagnostics(summary_path, db_path, resolved_policy_file)


if __name__ == "__main__":
    main()
