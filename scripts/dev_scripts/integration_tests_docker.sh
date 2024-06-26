#!/bin/bash

# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script runs the integration tests using Macaron as a Docker image. The image tag to run the integration tests
# against will follow the environment variable MACARON_IMAGE_TAG.

# The current workspace.
WORKSPACE=$1

# The location to the run_macaron.sh script.
RUN_MACARON_SCRIPT=$2

# The scripts to compare the results of the integration tests.
COMPARE_DEPS=$WORKSPACE/tests/dependency_analyzer/compare_dependencies.py
COMPARE_POLICIES=$WORKSPACE/tests/policy_engine/compare_policy_reports.py
COMPARE_VSA=$WORKSPACE/tests/vsa/compare_vsa.py
UNIT_TEST_SCRIPT=$WORKSPACE/scripts/dev_scripts/test_run_macaron_sh.py
RUN_POLICY="$RUN_MACARON_SCRIPT verify-policy"
DB=$WORKSPACE/output/macaron.db
MAKE_VENV="python -m venv"

RESULT_CODE=0

function run_macaron_clean() {
    rm $DB
    $RUN_MACARON_SCRIPT "$@"
}

function log_fail() {
    printf "Error: FAILED integration test (line ${BASH_LINENO}) %s\n" $@
    RESULT_CODE=1
}

python ./tests/integration/run.py run \
    --macaron scripts/release_scripts/run_macaron.sh \
    --include-tag shared-docker-python \
    ./tests/integration/cases/... || log_fail

if [ $RESULT_CODE -ne 0 ];
then
    exit 1
fi
