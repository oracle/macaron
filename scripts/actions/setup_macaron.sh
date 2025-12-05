#!/usr/bin/env bash

# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
set -euo pipefail

MACARON_DIR="${RUNNER_TEMP:-/tmp}/macaron"

mkdir -p "$MACARON_DIR"
cd "$MACARON_DIR"

# Download image using macaron_image_tag else latest release
if [ "${MACARON_IMAGE_TAG}" != "latest" ]; then
    echo "MACARON_IMAGE_TAG detected: ${MACARON_IMAGE_TAG}"
    URL="https://raw.githubusercontent.com/oracle/macaron/refs/tags/${MACARON_IMAGE_TAG}/scripts/release_scripts/run_macaron.sh"
    SCRIPT_NAME="run_macaron_${MACARON_IMAGE_TAG}.sh"
else
    echo "Using default latest release."
    URL="https://raw.githubusercontent.com/oracle/macaron/release/scripts/release_scripts/run_macaron.sh"
    SCRIPT_NAME="run_macaron.sh"
fi

# Get the run_macaron.sh script
if [ ! -f "$SCRIPT_NAME" ]; then
  echo "Downloading $SCRIPT_NAME from: $URL"
  curl -fSL -o "$SCRIPT_NAME" "$URL"
else
  echo "$SCRIPT_NAME already exists, skipping download."
fi

chmod +x "$SCRIPT_NAME"
echo "MACARON=$MACARON_DIR/$SCRIPT_NAME" >> "$GITHUB_ENV"
