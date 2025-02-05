#!/usr/bin/env bash

# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

#
# Checks if the files in tests/malware_analyzer/pypi/resources/sourcecode_samples have executable permissions,
# failing if any do.
#

MACARON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../.. && pwd)"
SAMPLES_PATH="${MACARON_DIR}/tests/malware_analyzer/pypi/resources/sourcecode_samples"

# any files have any of the executable bits set
executables=$(find "$SAMPLES_PATH" -type f -perm -u+x -o -type f -perm -g+x -o -type f -perm -o+x)
if [ -n "$executables" ]; then
    echo "The following files should not have any executable permissions:"
    echo "$executables"
    exit 1
fi
