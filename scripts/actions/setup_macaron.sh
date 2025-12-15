#!/usr/bin/env bash

# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
set -euo pipefail

MACARON_DIR="${RUNNER_TEMP:-/tmp}/macaron"
mkdir -p "$MACARON_DIR"

ACTION_DIR="${RUNNER_TEMP:-/tmp}/macaron-action"
rm -rf "$ACTION_DIR"
mkdir -p "$ACTION_DIR"

git clone --filter=blob:none --no-checkout https://github.com/oracle/macaron.git "$ACTION_DIR"

TARGET_REF="${ACTION_REF:-main}"
MACARON_IMAGE_TAG=""
cd "$ACTION_DIR"
if [[ "$TARGET_REF" =~ ^[0-9a-f]{40}$ ]]; then
    # Check for tags pointing directly at the SHA.
    tags=$(git tag --points-at "$TARGET_REF")
    if [[ -n "$tags" ]]; then
        # Get the first tag (main or first one listed)
        MACARON_IMAGE_TAG="$(echo "$tags" | head -n1)"
        echo "SHA $TARGET_REF maps to exact tag: $MACARON_IMAGE_TAG"
    else
        # Search all tags that contain the commit (could be ancestor).
        history_tags=$(git tag --contains "$TARGET_REF")
        if [[ -n "$history_tags" ]]; then
            MACARON_IMAGE_TAG="$(echo "$history_tags" | head -n1)"
            echo "SHA $TARGET_REF is contained in tag: $MACARON_IMAGE_TAG"
        else
            echo "No tag found for SHA $TARGET_REF. Defaulting to 'latest'."
            MACARON_IMAGE_TAG="latest"
        fi
    fi
elif [[ "$TARGET_REF" =~ ^v[0-9] ]]; then
    MACARON_IMAGE_TAG="$TARGET_REF"
    echo "Ref is a direct tag: $MACARON_IMAGE_TAG"
else
    echo "Using 'latest' image."
    MACARON_IMAGE_TAG="latest"
fi

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
echo "MACARON_IMAGE_TAG=${MACARON_IMAGE_TAG}" >> "$GITHUB_ENV"
