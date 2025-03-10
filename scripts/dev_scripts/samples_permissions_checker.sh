#!/usr/bin/env bash

# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

#
# Checks if the files in tests/malware_analyzer/pypi/resources/sourcecode_samples have executable permissions,
# failing if any do.
#

# Strict bash options.
#
# -e:          exit immediately if a command fails (with non-zero return code),
#              or if a function returns non-zero.
#
# -u:          treat unset variables and parameters as error when performing
#              parameter expansion.
#              In case a variable ${VAR} is unset but we still need to expand,
#              use the syntax ${VAR:-} to expand it to an empty string.
#
# -o pipefail: set the return value of a pipeline to the value of the last
#              (rightmost) command to exit with a non-zero status, or zero
#              if all commands in the pipeline exit successfully.
#
# Reference: https://www.gnu.org/software/bash/manual/html_node/The-Set-Builtin.html.
set -euo pipefail

MACARON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../.. && pwd)"
SAMPLES_PATH="${MACARON_DIR}/tests/malware_analyzer/pypi/resources/sourcecode_samples"

# any files have any of the executable bits set
executables=$( ( find "$SAMPLES_PATH" -type f -perm -u+x -o -type f -perm -g+x -o -type f -perm -o+x | sed "s|$MACARON_DIR/||"; git ls-files "$SAMPLES_PATH" --full-name) | sort | uniq -d)
if [ -n "$executables" ]; then
    echo "The following files should not have any executable permissions:"
    echo "$executables"
    exit 1
fi
