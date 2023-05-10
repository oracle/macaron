#!/bin/bash

# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script runs the integration tests using Macaron as a Docker image. The image tag to run the integration tests
# against will follow the environment variable MACARON_IMAGE_TAG.

# The current workspace.
WORKSPACE=$1

# The location to the run_macaron.sh script.
RUN_MACARON_SCRIPT=$2

# The scripts to compare the results of the integration tests.
COMPARE_DEPS=$WORKSPACE/tests/dependency_analyzer/compare_dependencies.py
COMPARE_JSON_OUT=$WORKSPACE/tests/e2e/compare_e2e_result.py

RESULT_CODE=0

if [[ -z "${GITHUB_TOKEN}" ]]
then
  echo "Environment variable GITHUB_TOKEN not set."
  exit 1
fi

function log_fail() {
    printf "Error: FAILED integration test (line ${BASH_LINENO}) %s\n" $@
    RESULT_CODE=1
}

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check the resolved dependency output with config for cyclonedx maven plugin (default)."
echo -e "----------------------------------------------------------------------------------\n"
DEP_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/dependencies.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_apache_maven.json

$RUN_MACARON_SCRIPT -t $GITHUB_TOKEN analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/maven_config.yaml || log_fail
$COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: e2e using the local repo path, the branch name and the commit digest without dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/maven.json
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/maven/maven.json

$RUN_MACARON_SCRIPT -lr $WORKSPACE/output/git_repos/github_com -t $GITHUB_TOKEN analyze -r apache/maven -b master -d 6767f2500f1d005924ccff27f04350c253858a84 --skip-deps || log_fail
$COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

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

$RUN_MACARON_SCRIPT -t $GITHUB_TOKEN analyze -c $WORKSPACE/tests/e2e/configurations/maven_config.yaml --skip-deps || log_fail

for i in "${COMPARE_FILES[@]}"
do
    $COMPARE_JSON_OUT $JSON_RESULT_DIR/$i $JSON_EXPECT_DIR/$i || log_fail
done

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing the repo path, the branch name and the commit digest with dependency resolution using a CycloneDx SBOM."
echo -e "----------------------------------------------------------------------------------\n"
SBOM_FILE=$WORKSPACE/tests/dependency_analyzer/cyclonedx/resources/apache_maven_root_sbom.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/apache_maven_with_sbom_provided.json
DEP_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/dependencies.json

$RUN_MACARON_SCRIPT -t $GITHUB_TOKEN analyze -rp https://github.com/apache/maven -b master -d 6767f2500f1d005924ccff27f04350c253858a84 -sbom $SBOM_FILE || log_fail

$COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "urllib3/urllib3: Analyzing the repo path when automatic dependency resolution is skipped."
echo "The CUE expectation file is provided as a single file path."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/urllib3/urllib3.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/urllib3/urllib3/urllib3.json
CUE_POLICY=$WORKSPACE/tests/policy_engine/resources/policies/urllib3/urllib3.cue
$RUN_MACARON_SCRIPT -t $GITHUB_TOKEN analyze -pe $CUE_POLICY -rp https://github.com/urllib3/urllib3/urllib3 -b main -d 87a0ecee6e691fe5ff93cd000c0158deebef763b --skip-deps || log_fail

$COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "urllib3/urllib3: Analyzing the repo path when automatic dependency resolution is skipped."
echo "The CUE expectation file and datalog policy should be found via the directory path."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/urllib3/urllib3_cue_datalog.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/urllib3/urllib3/urllib3.json
POLICY_DIR=$WORKSPACE/tests/policy_engine/resources/policies/urllib3/
$RUN_MACARON_SCRIPT -t $GITHUB_TOKEN analyze -pe $POLICY_DIR -rp https://github.com/urllib3/urllib3/urllib3 -b main -d 87a0ecee6e691fe5ff93cd000c0158deebef763b --skip-deps || log_fail

$COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "slsa-framework/slsa-verifier: Analyzing the repo path when automatic dependency resolution is skipped"
echo "and Datalog file is provided as expectation."
echo -e "----------------------------------------------------------------------------------\n"
JSON_RESULT=$WORKSPACE/output/reports/github_com/slsa-framework/slsa-verifier/slsa-verifier.json
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/slsa-verifier/slsa-verifier_datalog.json
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/valid/slsa-verifier.dl

$RUN_MACARON_SCRIPT -t $GITHUB_TOKEN analyze -pe $POLICY_FILE -rp https://github.com/slsa-framework/slsa-verifier -b main -d fc50b662fcfeeeb0e97243554b47d9b20b14efac --skip-deps || log_fail

$COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "Test verifying YAML-based provenance expectation."
echo -e "----------------------------------------------------------------------------------\n"
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/slsa_verifier.yaml
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/slsa-verifier/slsa-verifier_yaml_poc.json

$RUN_MACARON_SCRIPT -t $GITHUB_TOKEN analyze -pe $POLICY_FILE -rp https://github.com/slsa-framework/slsa-verifier -b main -d fc50b662fcfeeeb0e97243554b47d9b20b14efac --skip-deps || log_fail

$COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "Run policy CLI with slsa-verifier results."
echo -e "----------------------------------------------------------------------------------\n"
COMPARE_POLICIES=$WORKSPACE/tests/policy_engine/compare_policy_reports.py
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/valid/slsa-verifier.dl
POLICY_RESULT=$WORKSPACE/output/policy_report.json
POLICY_EXPECTED=$WORKSPACE/tests/policy_engine/expected_results/policy_report.json

# Run policy engine on the database and compare results.
$RUN_MACARON_SCRIPT verify-policy -f $POLICY_FILE -d "$WORKSPACE/output/macaron.db" || log_fail
python $COMPARE_POLICIES $POLICY_RESULT $POLICY_EXPECTED || log_fail

if [ $RESULT_CODE -ne 0 ];
then
    exit 1
fi
