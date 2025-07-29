#!/usr/bin/env bash

# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

#
# This script fetches the list of top PyPI packages and saves them to a file.
# It downloads the data from https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.json,
# extracts the top 5000 package names using jq, and saves them to the specified location.
#
# If the destination file already exists, the script will do nothing.
#
# Usage: ./find_packages.sh [FOLDER] [FILE]
#   - FOLDER: The destination folder (default: ../src/macaron/resources)
#   - FILE: The destination filename (default: popular_packages.txt)
#
# Dependencies: curl, jq.

# Set default values
DEFAULT_FOLDER="../src/macaron/resources"
DEFAULT_FILE="popular_packages.txt"

# Override with provided arguments if they exist
FOLDER=${1:-$DEFAULT_FOLDER}
FILE=${2:-$DEFAULT_FILE}

FULL_PATH="$FOLDER/$FILE"
URL="https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.json"

# Check if file exists
if [ -f "$FULL_PATH" ]; then
    echo "$FULL_PATH already exists. Nothing to do."
else
    echo "$FULL_PATH not found. Fetching top PyPI packages..."

    # Ensure the directory exists
    mkdir -p "$FOLDER"

    # Fetch and process JSON using curl and jq
    if curl -s "$URL" | jq -r '.rows[:5000] | sort_by(-.download_count) | .[].project' > "$FULL_PATH"; then
        echo "Successfully saved top 5000 packages to $FULL_PATH"
    else
        echo "Failed to fetch or process package data."
        exit 1
    fi
fi
