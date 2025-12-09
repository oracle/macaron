#!/usr/bin/env bash

# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
set -euo pipefail

# Run `macaron analyze` using environment variables passed from the action.

if [ -z "${MACARON:-}" ]; then
  echo "MACARON is not set. Did the setup step run?"
  exit 1
fi

CMD=""
if [ -n "${DEFAULTS_PATH:-}" ]; then
  CMD="$MACARON --defaults-path ${DEFAULTS_PATH}"
else
  CMD="$MACARON"
fi

OUTPUT_DIR=${OUTPUT_DIR:-output}
CMD="$CMD --output ${OUTPUT_DIR} -lr . analyze"

if [ -n "${REPO_PATH:-}" ]; then
  CMD="$CMD -rp ${REPO_PATH}"
elif [ -n "${PACKAGE_URL:-}" ]; then
  CMD="$CMD -purl ${PACKAGE_URL}"
fi

if [ -n "${BRANCH:-}" ]; then
  CMD="$CMD --branch ${BRANCH}"
fi

if [ -n "${DIGEST:-}" ]; then
  CMD="$CMD --digest ${DIGEST}"
fi

CMD="$CMD --deps-depth ${DEPS_DEPTH:-0}"

if [ -n "${SBOM_PATH:-}" ]; then
  CMD="$CMD --sbom-path ${SBOM_PATH}"
fi

if [ -n "${PYTHON_VENV:-}" ]; then
  CMD="$CMD --python-venv ${PYTHON_VENV}"
fi

if [ -n "${PROVENANCE_FILE:-}" ]; then
  CMD="$CMD --provenance-file ${PROVENANCE_FILE}"
fi

if [ -n "${PROVENANCE_EXPECTATION:-}" ]; then
  CMD="$CMD --provenance-expectation ${PROVENANCE_EXPECTATION}"
fi

echo "Executing: $CMD"
eval "$CMD"
