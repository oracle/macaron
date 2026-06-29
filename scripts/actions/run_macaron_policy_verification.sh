#!/usr/bin/env bash

# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
set -euo pipefail

# Run `macaron verify-policy` using a local policy file or a predefined policy and PURL.
#
# Outputs written to GitHub Actions:
# - `policy_report` and `vsa_report` are emitted to `$GITHUB_OUTPUT` when
#   the verification command succeeds and files are produced.

if [ -z "${MACARON:-}" ]; then
  echo "MACARON is not set. Did the setup step run?"
  exit 1
fi

run_macaron() {
  printf 'Executing:'
  printf ' %q' "$@"
  printf '\n'
  "$@"
}

DEFAULTS_PATH=${DEFAULTS_PATH:-}
OUTPUT_DIR=${OUTPUT_DIR:-output}
FILE=${POLICY_FILE:-}
PURL=${POLICY_PURL:-}

CMD=("$MACARON")
if [ -n "$DEFAULTS_PATH" ]; then
  CMD+=(--defaults-path "$DEFAULTS_PATH")
fi
CMD+=(--output "$OUTPUT_DIR" verify-policy --database "${OUTPUT_DIR}/macaron.db")

if [ -n "$FILE" ] && [ -f "$FILE" ]; then
  CMD+=(--file "$FILE")

  if run_macaron "${CMD[@]}"; then
    echo "policy_report=${OUTPUT_DIR}/policy_report.json" >> "$GITHUB_OUTPUT"
    if [ -f "${OUTPUT_DIR}/vsa.intoto.jsonl" ]; then
      echo "vsa_report=${OUTPUT_DIR}/vsa.intoto.jsonl" >> "$GITHUB_OUTPUT"
    else
      echo "vsa_report=VSA Not Generated." >> "$GITHUB_OUTPUT"
    fi
  fi
elif [ -n "$FILE" ] && [ -n "$PURL" ]; then
  CMD+=(--existing-policy "$FILE" --package-url "$PURL")

  if run_macaron "${CMD[@]}"; then
    echo "policy_report=${OUTPUT_DIR}/policy_report.json" >> "$GITHUB_OUTPUT"
    if [ -f "${OUTPUT_DIR}/vsa.intoto.jsonl" ]; then
      echo "vsa_report=${OUTPUT_DIR}/vsa.intoto.jsonl" >> "$GITHUB_OUTPUT"
    else
      echo "vsa_report=VSA Not Generated." >> "$GITHUB_OUTPUT"
    fi
  fi
else
  echo "No valid policy inputs found"
fi
