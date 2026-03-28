#!/usr/bin/env bash

# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-output}"
DB_PATH="${OUTPUT_DIR}/macaron.db"
POLICY_REPORT="${POLICY_REPORT:-${OUTPUT_DIR}/policy_report.json}"
HTML_REPORT_PATH="${HTML_REPORT_PATH:-}"
VSA_PATH="${VSA_PATH:-${OUTPUT_DIR}/vsa.intoto.jsonl}"
REPORTS_ARTIFACT_NAME="${REPORTS_ARTIFACT_NAME:-macaron-reports}"
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
REPORTS_ARTIFACT_URL="${REPORTS_ARTIFACT_URL:-${RUN_URL}}"

{
  echo "## Macaron Analysis Results"
  echo
  echo "Download reports from this artifact link:"
  echo "- [\`${REPORTS_ARTIFACT_NAME}\`](${REPORTS_ARTIFACT_URL})"
  echo
  echo "Generated files:"
  if [ -n "${HTML_REPORT_PATH}" ]; then
    echo "- HTML report: \`${HTML_REPORT_PATH}\`"
  fi
  echo "- Database: \`${DB_PATH}\`"
  echo "- Policy report: \`${POLICY_REPORT}\`"
  if [ -n "${VSA_PATH}" ] && [ -f "${VSA_PATH}" ]; then
    echo "- Policy status: :white_check_mark: Policy verification succeeded."
  else
    echo "- Policy status: :x: Policy verification failed."
  fi
  echo
} >> "${GITHUB_STEP_SUMMARY}"

if [ ! -f "${DB_PATH}" ]; then
  echo ":warning: Macaron database was not generated." >> "${GITHUB_STEP_SUMMARY}"
  exit 0
fi

python - <<'PY'
import json
import os
import sqlite3

db_path = os.path.join(os.environ.get("OUTPUT_DIR", "output"), "macaron.db")
summary_path = os.environ["GITHUB_STEP_SUMMARY"]

with sqlite3.connect(db_path) as conn:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT github_actions_id, github_actions_version, vulnerability_urls, caller_workflow
        FROM github_actions_vulnerabilities_check
        ORDER BY id
        """
    )
    rows = cur.fetchall()

with open(summary_path, "a", encoding="utf-8") as f:
    if not rows:
        f.write(":white_check_mark: No vulnerable GitHub Actions detected.\n")
    else:
        f.write("| Action | Version | Vulnerabilities | Workflow |\n")
        f.write("|---|---|---|---|\n")
        for action_id, version, vulnerability_urls, caller_workflow in rows:
            vuln_value = vulnerability_urls
            try:
                parsed = json.loads(vulnerability_urls)
                if isinstance(parsed, list):
                    vuln_value = ", ".join(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

            f.write(
                f"| `{action_id}` | `{version}` | `{vuln_value}` | {caller_workflow} |\n"
            )
PY
