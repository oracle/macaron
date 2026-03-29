#!/usr/bin/env bash

# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-output}"
DB_PATH="${DB_PATH:-${OUTPUT_DIR}/macaron.db}"
POLICY_REPORT="${POLICY_REPORT:-${OUTPUT_DIR}/policy_report.json}"
POLICY_FILE="${POLICY_FILE:-}"
HTML_REPORT_PATH="${HTML_REPORT_PATH:-}"
VSA_PATH="${VSA_PATH:-${OUTPUT_DIR}/vsa.intoto.jsonl}"
UPLOAD_REPORTS="${UPLOAD_REPORTS:-true}"
REPORTS_ARTIFACT_NAME="${REPORTS_ARTIFACT_NAME:-macaron-reports}"
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
REPORTS_ARTIFACT_URL="${REPORTS_ARTIFACT_URL:-${RUN_URL}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python "${SCRIPT_DIR}/write_job_summary.py"
