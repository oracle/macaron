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

echo -e "\n----------------------------------------------------------------------------------"
echo "Run unit tests for the run_macaron.sh script"
python $UNIT_TEST_SCRIPT || log_fail
echo -e "\n----------------------------------------------------------------------------------"

echo -e "\n----------------------------------------------------------------------------------"
echo "pkg:pypi/django@5.0.6: Analyzing the dependencies with virtual env provided as input."
echo -e "----------------------------------------------------------------------------------\n"
# Prepare the virtual environment.
VIRTUAL_ENV_PATH=$WORKSPACE/.django_venv
$MAKE_VENV "$VIRTUAL_ENV_PATH"
"$VIRTUAL_ENV_PATH"/bin/pip install django==5.0.6
run_macaron_clean analyze -purl pkg:pypi/django@5.0.6 --python-venv "$VIRTUAL_ENV_PATH" || log_fail

# Check the dependencies using the policy engine.
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/django/test_dependencies.dl
POLICY_RESULT=$WORKSPACE/output/policy_report.json
POLICY_EXPECTED=$WORKSPACE/tests/policy_engine/expected_results/django/test_dependencies.json

$RUN_POLICY -f "$POLICY_FILE" -d $DB || log_fail
python $COMPARE_POLICIES $POLICY_RESULT $POLICY_EXPECTED || log_fail

# Clean up and remove the virtual environment.
rm -rf "$VIRTUAL_ENV_PATH"

python3 ./tests/integration/run.py run \
    --macaron scripts/release_scripts/run_macaron.sh \
    --include-tag docker \
    ./tests/integration/cases/... || log_fail

if [ $RESULT_CODE -ne 0 ];
then
    exit 1
fi
