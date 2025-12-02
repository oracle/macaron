#!/usr/bin/env bash

# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
set -euo pipefail

# Setup Macaron virtualenv and make available via GitHub Actions environment files.
# This script writes `MACARON=<path>` to `$GITHUB_ENV` so later steps can invoke the macaron CLI, and appends the venv `bin` directory to `$GITHUB_PATH`.

MACARON_DIR="${RUNNER_TEMP:-/tmp}/macaron"
VENV_MACARON="$MACARON_DIR/.venv/bin/macaron"

mkdir -p "$MACARON_DIR"

if [ -x "$VENV_MACARON" ]; then
  echo "Using macaron from existing venv: $VENV_MACARON"
  echo "MACARON=$VENV_MACARON" >> "$GITHUB_ENV"
  echo "$MACARON_DIR/.venv/bin" >> "$GITHUB_PATH"
  exit 0
fi

cd "$MACARON_DIR"
git clone https://github.com/oracle/macaron.git .
make venv
export PATH="$MACARON_DIR/.venv/bin:$PATH"
make setup
echo "MACARON=$VENV_MACARON" >> "$GITHUB_ENV"
echo "$MACARON_DIR/.venv/bin" >> "$GITHUB_PATH"
