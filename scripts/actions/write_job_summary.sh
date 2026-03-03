#!/usr/bin/env bash

# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-output}"
DB_PATH="${OUTPUT_DIR}/macaron.db"
POLICY_REPORT="${POLICY_REPORT:-${OUTPUT_DIR}/policy_report.json}"
VSA_PATH="${OUTPUT_DIR}/vsa.intoto.jsonl"
VSA_GENERATED="${VSA_GENERATED:-false}"
REPORTS_ARTIFACT_NAME="${REPORTS_ARTIFACT_NAME:-macaron-reports}"
VSA_ARTIFACT_NAME="${VSA_ARTIFACT_NAME:-${REPORTS_ARTIFACT_NAME}-vsa}"
ARTIFACTS_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/artifacts"

{
  echo "## Macaron GitHub Actions Vulnerability Results"
  echo
  echo "- Database: [\`${DB_PATH}\`](${ARTIFACTS_URL})"
  echo "- Policy report: [\`${POLICY_REPORT}\`](${ARTIFACTS_URL})"
  echo "- VSA generated: \`${VSA_GENERATED}\`"
  echo "- Download artifact: [\`${REPORTS_ARTIFACT_NAME}\`](${ARTIFACTS_URL})"
  if [ "${VSA_GENERATED}" = "true" ]; then
    echo "- Download VSA: [\`${VSA_ARTIFACT_NAME}\`](${ARTIFACTS_URL})"
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

if [ -f "${VSA_PATH}" ]; then
  echo >> "${GITHUB_STEP_SUMMARY}"
  echo ":white_check_mark: VSA was generated at \`${VSA_PATH}\`." >> "${GITHUB_STEP_SUMMARY}"
else
  echo >> "${GITHUB_STEP_SUMMARY}"
  echo ":warning: VSA was not generated at \`${VSA_PATH}\`." >> "${GITHUB_STEP_SUMMARY}"
fi
