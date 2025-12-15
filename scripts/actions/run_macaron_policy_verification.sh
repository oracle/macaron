#!/usr/bin/env bash

# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
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

DEFAULTS_PATH=${DEFAULTS_PATH:-}
OUTPUT_DIR=${OUTPUT_DIR:-output}
FILE=${POLICY_FILE:-}
PURL=${POLICY_PURL:-}

if [ -n "$DEFAULTS_PATH" ]; then
  CMD="$MACARON --defaults-path ${DEFAULTS_PATH}"
else
  CMD="$MACARON"
fi
CMD="$CMD --output ${OUTPUT_DIR} verify-policy --database ${OUTPUT_DIR}/macaron.db"

if [ -n "$FILE" ] && [ -f "$FILE" ]; then
  CMD="$CMD --file $FILE"

  echo "Executing: $CMD"
  if eval "$CMD"; then
    echo "policy_report=${OUTPUT_DIR}/policy_report.json" >> "$GITHUB_OUTPUT"
    if [ -f "${OUTPUT_DIR}/vsa.intoto.jsonl" ]; then
      echo "vsa_report=${OUTPUT_DIR}/vsa.intoto.jsonl" >> "$GITHUB_OUTPUT"
    else
      echo "vsa_report=VSA Not Generated." >> "$GITHUB_OUTPUT"
    fi
  fi
elif [ -n "$PURL" ]; then
  CMD="$CMD --existing-policy ${FILE} --package-url ${PURL}"

  echo "Executing: $CMD"
  echo "$CMD"
  if eval "$CMD"; then
    echo "policy_report=${OUTPUT_DIR}/policy_report.json" >> "$GITHUB_OUTPUT"
    if [ -f "${OUTPUT_DIR}/vsa.intoto.jsonl" ]; then
      echo "vsa_report=${OUTPUT_DIR}/vsa.intoto.jsonl" >> "$GITHUB_OUTPUT"
    else
      echo "vsa_report=VSA Not Generated." >> "$GITHUB_OUTPUT"
    fi
  fi
else
  echo "No file or pre-defined policy found for ${FILE} and policy_purl ${PURL}"
fi
