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
from urllib.parse import urlsplit

CHECK_RESULT_DEFAULT_COLUMNS = [
    "component_id",
    "check_id",
    "passed",
]


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
        template_path = Path(
            os.path.join(
                action_path,
                "src",
                "macaron",
                "resources",
                "policies",
                "datalog",
                f"{policy_input}.dl.template",
            )
        )
        if template_path.is_file():
            return template_path, "predefined"

    return None, "unresolved"


def _resolve_existing_policy_sql(policy_name: str) -> Path | None:
    """Resolve SQL diagnostics query for a predefined policy name."""
    action_path = _env("GITHUB_ACTION_PATH", "")
    if not action_path:
        return None
    sql_path = Path(os.path.join(action_path, "src", "macaron", "resources", "policies", "sql", f"{policy_name}.sql"))
    return sql_path if sql_path.is_file() else None


def _write_header(
    summary_path: Path,
    db_path: Path,
    policy_report: str,
    policy_file: str,
    html_report: str,
    policy_provided: bool,
) -> None:
    upload_reports = _env("UPLOAD_REPORTS", "true").lower() == "true"
    output_dir = _env("OUTPUT_DIR", "output")
    reports_artifact_name = _env("REPORTS_ARTIFACT_NAME", "macaron-reports")
    run_url = (
        f"{_env('GITHUB_SERVER_URL', 'https://github.com')}/"
        f"{_env('GITHUB_REPOSITORY')}/actions/runs/{_env('GITHUB_RUN_ID')}"
    )
    reports_artifact_url = _env("REPORTS_ARTIFACT_URL", run_url)
    vsa_generated = _env("VSA_GENERATED", "").lower()
    if vsa_generated in {"true", "false"}:
        policy_succeeded = vsa_generated == "true"
    else:
        vsa_path = _env("VSA_PATH", f"{output_dir}/vsa.intoto.jsonl")
        policy_succeeded = bool(vsa_path) and Path(vsa_path).is_file()

    _append_line(summary_path, "## Macaron Analysis Results")
    _append_line(summary_path)
    if upload_reports:
        _append_line(summary_path, "Download reports from this artifact link:")
        _append_line(summary_path, f"- [`{reports_artifact_name}`]({reports_artifact_url})")
        _append_line(summary_path)
        _append_line(summary_path, "Generated files:")
        if html_report:
            _append_line(summary_path, f"- HTML report: `{html_report}`")
        _append_line(summary_path, f"- Database: `{db_path}`")
        if policy_provided:
            _append_line(summary_path, f"- Policy report: `{policy_report}`")
        _append_line(summary_path)

    if policy_provided:
        _append_line(summary_path, "Policy:")
        if policy_file:
            _append_line(summary_path, f"- Policy file: `{policy_file}`")
        if policy_succeeded:
            _append_line(summary_path, "- Policy status: :white_check_mark: Policy verification succeeded.")
        else:
            _append_line(summary_path, "- Policy status: :x: Policy verification failed.")
    else:
        _append_line(summary_path, "Policy:")
        _append_line(summary_path, "- No policy was provided.")
    _append_line(summary_path)


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


def _query_sql(conn: sqlite3.Connection, sql_query: str) -> tuple[list[str], list[tuple]]:
    # Python's sqlite cursor.execute() can fail when the SQL begins with line comments.
    # Strip leading SQL line comments while preserving the query body.
    sanitized_lines = []
    for line in sql_query.splitlines():
        if line.lstrip().startswith("--"):
            continue
        sanitized_lines.append(line)
    sanitized_query = "\n".join(sanitized_lines).strip()
    if not sanitized_query:
        return [], []

    cur = conn.cursor()
    cur.execute(sanitized_query)
    rows = cur.fetchall()
    columns = [col[0] for col in (cur.description or [])]
    return columns, rows


def _write_markdown_table(summary_path: Path, columns: list[str], rows: list[tuple]) -> bool:
    if not columns or not rows:
        return False

    _append_line(summary_path, f"| {' | '.join(columns)} |")
    _append_line(summary_path, f"|{'|'.join(['---'] * len(columns))}|")
    for row in rows:
        values = [_format_table_cell(value) for value in row]
        _append_line(summary_path, f"| {' | '.join(values)} |")
    return True


def _format_table_cell(value: object) -> str:
    text = str(value)
    parsed_list = _parse_list_cell(text)
    if parsed_list is not None:
        items = [_format_list_item(item) for item in parsed_list]
        return "<br>".join(f"- {item}" for item in items) if items else "`[]`"

    if text.startswith(("http://", "https://")):
        parsed = urlsplit(text)
        segments = [part for part in parsed.path.split("/") if part]
        label = segments[-1] if segments else parsed.netloc
        return f"[`{label}`]({text})"
    return f"`{_sanitize_for_markdown_table_code(text)}`"


def _parse_list_cell(text: str) -> list[object] | None:
    stripped = text.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return None
    try:
        loaded = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, list) else None


def _format_list_item(value: object) -> str:
    text = str(value)
    if text.startswith(("http://", "https://")):
        parsed = urlsplit(text)
        segments = [part for part in parsed.path.split("/") if part]
        label = segments[-1] if segments else parsed.netloc
        return f"[`{label}`]({text})"
    return f"`{_sanitize_for_markdown_table_code(text)}`"


def _sanitize_for_markdown_table_code(text: str) -> str:
    """Sanitize inline-code content for markdown table cells."""
    return text.replace("`", "'").replace("|", "\\|").replace("\n", " ")


def _priority_label(priority: object) -> str:
    """Map numeric priority to a concise severity-like label."""
    try:
        value = int(priority)
    except (TypeError, ValueError):
        return str(priority)

    if value >= 90:
        return "critical"
    if value >= 70:
        return "high"
    if value >= 50:
        return "medium"
    return "low"


def _gha_group_label(group: str) -> str:
    # finding_group is the top-level section key; finding_type is rendered per-row as the subtype.
    if group == "third_party_action_risk":
        return "Third-party action risks"
    if group == "workflow_security_issue":
        return "Workflow security issues"
    return group


def _extract_finding_summary(message: object) -> str:
    """Extract a compact summary from a finding message."""
    text = str(message).strip()
    if not text:
        return ""

    # Expected format: "Summary: ... Details: ... Recommendation: ..."
    match = re.search(r"Summary:\s*(.*?)(?:\s+Details:\s*|\s+Recommendation:\s*|$)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return text


def write_compact_gha_vuln_diagnostics(summary_path: Path, columns: list[str], rows: list[tuple]) -> bool:
    """Write compact GitHub Actions vulnerability diagnostics to the job summary.

    Parameters
    ----------
    summary_path : Path
        Path to the GitHub job summary markdown file.
    columns : list[str]
        Ordered column names from the SQL diagnostics query result.
    rows : list[tuple]
        Row values matching ``columns`` order.

    Returns
    -------
    bool
        ``True`` if content was rendered; ``False`` when inputs are empty.
    """
    if not columns or not rows:
        return False

    col_index = {name: idx for idx, name in enumerate(columns)}
    required = [
        "finding_priority",
        "finding_type",
        "action_name",
        "action_ref",
        "vulnerable_workflow",
    ]
    if any(name not in col_index for name in required):
        return _write_markdown_table(summary_path, columns, rows)

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            int(row[col_index["finding_priority"]]) if str(row[col_index["finding_priority"]]).isdigit() else 0
        ),
        reverse=True,
    )
    display_rows = sorted_rows[:10]
    group_idx = col_index.get("finding_group")

    _append_line(
        summary_path,
        "_Showing top 10 findings by priority. Expand details below for full diagnostics._",
    )
    preferred_groups = ["workflow_security_issue", "third_party_action_risk"]
    groups_in_rows: list[str] = []
    if group_idx is not None:
        discovered_groups = [str(row[group_idx]) for row in sorted_rows]
        groups_in_rows.extend([group for group in preferred_groups if group in discovered_groups])
        groups_in_rows.extend([group for group in discovered_groups if group not in groups_in_rows])
    else:
        groups_in_rows = ["all_findings"]

    for group in groups_in_rows:
        if group_idx is None:
            group_rows = display_rows
            title = "Findings"
        else:
            group_rows = [row for row in sorted_rows if str(row[group_idx]) == group][:10]
            if not group_rows:
                continue
            title = _gha_group_label(group)
        _append_line(summary_path)
        _append_line(summary_path, f"#### {title}")
        _append_line(summary_path)
        if group == "workflow_security_issue":
            _append_line(summary_path, "| priority | type | summary | workflow |")
            _append_line(summary_path, "|---|---|---|---|")
        else:
            _append_line(summary_path, "| priority | type | action | version | workflow |")
            _append_line(summary_path, "|---|---|---|---|---|")
        for row in group_rows:
            priority_raw = row[col_index["finding_priority"]]
            priority = f"`{_priority_label(priority_raw)} ({priority_raw})`"
            finding_type = _format_table_cell(row[col_index["finding_type"]])
            finding_summary = _format_table_cell(
                _extract_finding_summary(row[col_index["finding_message"]]) if "finding_message" in col_index else ""
            )
            action_name = _format_table_cell(row[col_index["action_name"]])
            action_version = _format_table_cell(row[col_index["action_ref"]])
            workflow = _format_table_cell(row[col_index["vulnerable_workflow"]])
            if group == "workflow_security_issue":
                _append_line(
                    summary_path,
                    f"| {priority} | {finding_type} | {finding_summary} | {workflow} |",
                )
            else:
                _append_line(
                    summary_path,
                    f"| {priority} | {finding_type} | {action_name} | {action_version} | {workflow} |",
                )

    _append_line(summary_path)
    _append_line(summary_path, "<details>")
    _append_line(summary_path, "<summary>Detailed findings</summary>")
    _append_line(summary_path)
    detail_groups = groups_in_rows if groups_in_rows else ["all_findings"]
    row_counter = 1
    for group in detail_groups:
        if group_idx is None:
            group_rows = sorted_rows
            title = "Findings"
        else:
            group_rows = [row for row in sorted_rows if str(row[group_idx]) == group]
            if not group_rows:
                continue
            title = _gha_group_label(group)
        _append_line(summary_path, f"**{title}**")
        for row in group_rows:
            action = str(row[col_index["action_name"]])
            version = str(row[col_index["action_ref"]])
            priority = row[col_index["finding_priority"]]
            finding_type = str(row[col_index["finding_type"]])
            workflow = str(row[col_index["vulnerable_workflow"]])
            if group == "workflow_security_issue":
                subject = workflow
            else:
                subject = f"{action}@{version}" if version else action
            _append_line(summary_path, f"{row_counter}. **`{subject}`** (`{finding_type}`, priority `{priority}`)")
            _append_line(summary_path, f"- Workflow: `{workflow}`")

            pin_idx = col_index.get("sha_pinned")
            row_group = str(row[group_idx]) if group_idx is not None else ""
            if pin_idx is not None and row_group == "third_party_action_risk" and row[pin_idx] is not None:
                pin_state = "yes" if bool(row[pin_idx]) else "no"
                _append_line(summary_path, f"- Pinned to full commit SHA: `{pin_state}`")

            vul_idx = col_index.get("vuln_urls")
            if vul_idx is not None and row[vul_idx]:
                parsed = _parse_list_cell(str(row[vul_idx]))
                if parsed:
                    _append_line(summary_path, "- Vulnerabilities:")
                    for item in parsed:
                        _append_line(summary_path, f"  - {_format_list_item(item)}")

            rec_idx = col_index.get("recommended_ref")
            if rec_idx is not None and row[rec_idx]:
                _append_line(summary_path, f"- Recommended ref: {_format_table_cell(row[rec_idx])}")

            msg_idx = col_index.get("finding_message")
            if msg_idx is not None and row[msg_idx]:
                _append_line(summary_path, f"- Details: {_format_table_cell(row[msg_idx])}")
            _append_line(summary_path)
            row_counter += 1
    _append_line(summary_path, "</details>")
    return True


def _write_policy_check_lists(summary_path: Path, policy_check_ids: list[str]) -> None:

    if policy_check_ids:
        _append_line(
            summary_path,
            f"- Checks referenced in policy: {', '.join(f'`{name}`' for name in policy_check_ids)}",
        )


def _write_custom_policy_failure_diagnostics(summary_path: Path, db_path: Path, policy_file: Path) -> None:
    check_relations, policy_check_ids = _parse_policy_checks(policy_file)
    has_details = False

    _append_line(summary_path)
    _append_line(summary_path, "### Policy Failure Diagnostics")
    _write_policy_check_lists(summary_path, policy_check_ids)
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
    has_details = False

    _append_line(summary_path)
    _append_line(summary_path, f"### Policy Failure Diagnostics ({policy_name})")
    _write_policy_check_lists(summary_path, policy_check_ids)
    if check_relations or policy_check_ids:
        has_details = True

    sql_path = _resolve_existing_policy_sql(policy_name)
    if sql_path:
        sql_query = sql_path.read_text(encoding="utf-8")
        with sqlite3.connect(db_path) as conn:
            cols, rows = _query_sql(conn, sql_query)
        if cols and rows:
            _append_line(summary_path)
            _append_line(summary_path, f"#### Results")
            if policy_name == "check-github-actions":
                rendered = write_compact_gha_vuln_diagnostics(summary_path, cols, rows)
            else:
                rendered = _write_markdown_table(summary_path, cols, rows)
            if rendered:
                has_details = True

    if not has_details:
        _append_line(summary_path, "- Additional check-level details are unavailable for this failure.")


def main() -> None:
    output_dir = Path(_env("OUTPUT_DIR", "output"))
    db_path = Path(_env("DB_PATH", os.path.join(str(output_dir), "macaron.db")))
    policy_report = _env("POLICY_REPORT", os.path.join(str(output_dir), "policy_report.json"))
    policy_file_value = _env("POLICY_FILE", "")
    resolved_policy_file, policy_mode = _resolve_policy_source(policy_file_value)
    policy_label = ""
    if policy_mode == "file" and resolved_policy_file:
        policy_label = str(resolved_policy_file)
    elif policy_mode == "predefined" and resolved_policy_file:
        policy_label = f"{policy_file_value}"
    elif policy_mode == "unresolved":
        policy_label = f"{policy_file_value} (unresolved)"
    html_report = _env("HTML_REPORT_PATH", "")
    vsa_path_value = _env("VSA_PATH", os.path.join(str(output_dir), "vsa.intoto.jsonl"))
    vsa_path = Path(vsa_path_value) if vsa_path_value else None

    summary_output = _env("GITHUB_STEP_SUMMARY")
    if not summary_output:
        raise RuntimeError("GITHUB_STEP_SUMMARY is not set.")
    summary_path = Path(summary_output)

    policy_provided = bool(policy_file_value.strip())
    _write_header(summary_path, db_path, policy_report, policy_label, html_report, policy_provided)

    if not db_path.is_file():
        _append_line(summary_path, ":warning: Macaron database was not generated.")
        return

    if (not vsa_path or not vsa_path.is_file()) and resolved_policy_file and resolved_policy_file.is_file():
        if policy_mode == "predefined":
            _write_existing_policy_failure_diagnostics(summary_path, db_path, policy_file_value, resolved_policy_file)
        else:
            _write_custom_policy_failure_diagnostics(summary_path, db_path, resolved_policy_file)


if __name__ == "__main__":
    main()
