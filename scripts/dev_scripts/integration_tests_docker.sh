#!/bin/bash

# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script runs the integration tests using Macaron as a Docker image.

# The current workspace.
WORKSPACE=$1

# The version of Macaron Docker image to run the integration tests.
DOCKER_IMAGE_TAG=$2

# The location to the run_macaron.sh script.
RUN_MACARON_SCRIPT=$3

# The command to run the Docker container.
RUN_MACARON="$RUN_MACARON_SCRIPT -I $DOCKER_IMAGE_TAG -T $GH_TOKEN"

# We run the script directly as we are not running inside the Macaron builder image.
COMPARE_DEPS=$WORKSPACE/tests/dependency_analyzer/compare_dependencies.py
COMPARE_JSON_OUT=$WORKSPACE/tests/e2e/compare_e2e_result.py

RESULT_CODE=0

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check the resolved dependency output with config for osint maven plugin (default)."
echo -e "----------------------------------------------------------------------------------\n"
DEP_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/dependencies.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/osint_maven_apache_maven.json

$RUN_MACARON -C $WORKSPACE/tests/dependency_analyzer/configurations/maven_config.yaml || RESULT_CODE=1
$COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || RESULT_CODE=1

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: e2e using the local repo path, the branch name and the commit digest without dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/maven.json
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/maven/maven.json

$RUN_MACARON -L $WORKSPACE/output/git_repos/github_com -R apache/maven -B master -D 6767f2500f1d005924ccff27f04350c253858a84 --skip-deps || RESULT_CODE=1
$COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || RESULT_CODE=1

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check the e2e output JSON file with config and no dependency analyzing."
echo -e "----------------------------------------------------------------------------------\n"
JSON_RESULT_DIR=$WORKSPACE/output/reports/github_com/apache/maven
JSON_EXPECT_DIR=$WORKSPACE/tests/e2e/expected_results/maven

declare -a COMPARE_FILES=(
    "maven.json"
    "guava.json"
    "mockito.json"
)

$RUN_MACARON -C $WORKSPACE/tests/e2e/configurations/maven_config.yaml --skip-deps || RESULT_CODE=1

for i in "${COMPARE_FILES[@]}"
do
    $COMPARE_JSON_OUT $JSON_RESULT_DIR/$i $JSON_EXPECT_DIR/$i || RESULT_CODE=1
done

echo -e "\n----------------------------------------------------------------------------------"
echo "slsa-framework/slsa-verifier: Analyzing using the repo path when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
JSON_RESULT=$WORKSPACE/output/reports/github_com/slsa-framework/slsa-verifier/slsa-verifier.json
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/slsa-verifier/slsa-verifier.json

$RUN_MACARON -R https://github.com/slsa-framework/slsa-verifier -B main -D fc50b662fcfeeeb0e97243554b47d9b20b14efac --skip-deps || RESULT_CODE=1

$COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || RESULT_CODE=1

echo -e "\n----------------------------------------------------------------------------------"
echo "slsa-framework/slsa-verifier: Verify the provenance against a policy."
echo -e "----------------------------------------------------------------------------------\n"
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/slsa_verifier.yaml
PROVENANCE_FILE=$WORKSPACE/tests/policy_engine/resources/provenances/slsa-verifier-linux-amd64.intoto.jsonl

$RUN_MACARON -V -J $POLICY_FILE -K $PROVENANCE_FILE || RESULT_CODE=1

echo -e "\n----------------------------------------------------------------------------------"
echo "slsa-framework/slsa-verifier: Test the verify command with invalid options."
echo -e "----------------------------------------------------------------------------------\n"
declare -a ERROR_VERIFY_USAGE=(
    "$RUN_MACARON -V"
    "$RUN_MACARON -V -J $POLICY_FILE"
    "$RUN_MACARON -V -J $POLICY_FILE -K $WORKSPACE/this/file/does/not/exist.json"
    "$RUN_MACARON -V -J $WORKSPACE/this/file/does/not/exist.json -K $WORKSPACE/this/file/does/not/exist.json"
)

for i in "${ERROR_VERIFY_USAGE[@]}"
do
    $i
    if [ $? -eq 0 ];
    then
        echo -e "Expected non-zero status code but got $?."
        RESULT_CODE=1
    fi
done

if [ $RESULT_CODE -ne 0 ];
then
    exit 1
fi
