#!/usr/bin/env bash

# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
set -euo pipefail

MACARON_DIR="${RUNNER_TEMP:-/tmp}/macaron"

mkdir -p "$MACARON_DIR"
cd "$MACARON_DIR"

# Get the run_macaron.sh script
if [ ! -f "run_macaron.sh" ]; then
  curl -fSLO https://raw.githubusercontent.com/oracle/macaron/release/scripts/release_scripts/run_macaron.sh
else
  echo "run_macaron.sh already exists, skipping download."
fi

chmod +x run_macaron.sh
echo "MACARON=$MACARON_DIR/run_macaron.sh" >> "$GITHUB_ENV"
