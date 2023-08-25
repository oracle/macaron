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

function log_fail() {
    printf "Error: FAILED integration test (line ${BASH_LINENO}) %s\n" $@
    RESULT_CODE=1
}

echo -e "\n----------------------------------------------------------------------------------"
echo "timyarkov/multibuild_test: Analyzing the repo path, the branch name and the commit digest"
echo "with dependency resolution using cyclonedx Gradle plugin (default)."
echo -e "----------------------------------------------------------------------------------\n"
DEP_RESULT=$WORKSPACE/output/reports/github_com/timyarkov/multibuild_test/dependencies.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_timyarkov_multibuild_test.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/timyarkov/multibuild_test/multibuild_test.json
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/multibuild_test/multibuild_test.json
$RUN_MACARON_SCRIPT analyze -rp https://github.com/timyarkov/multibuild_test -b main -d a8b0efe24298bc81f63217aaa84776c3d48976c5 || log_fail

$COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

$COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check the resolved dependency output with config for cyclonedx maven plugin (default)."
echo -e "----------------------------------------------------------------------------------\n"
DEP_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/dependencies.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_apache_maven.json

$RUN_MACARON_SCRIPT analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/maven_config.yaml || log_fail
$COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: e2e using the local repo path, the branch name and the commit digest without dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/maven.json
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/maven/maven.json

$RUN_MACARON_SCRIPT -lr $WORKSPACE/output/git_repos/github_com analyze -r apache/maven -b master -d 6767f2500f1d005924ccff27f04350c253858a84 --skip-deps || log_fail
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

$RUN_MACARON_SCRIPT analyze -c $WORKSPACE/tests/e2e/configurations/maven_config.yaml --skip-deps || log_fail

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

$RUN_MACARON_SCRIPT analyze -rp https://github.com/apache/maven -b master -d 6767f2500f1d005924ccff27f04350c253858a84 -sbom $SBOM_FILE || log_fail

$COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing with PURL and repository path without dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/purl/maven/maven.json
JSON_RESULT=$WORKSPACE/output/reports/maven/apache/maven/maven.json
$RUN_MACARON_SCRIPT analyze -purl pkg:maven/apache/maven -rp https://github.com/apache/maven -b master -d 6767f2500f1d005924ccff27f04350c253858a84 --skip-deps || log_fail

$COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "urllib3/urllib3: Analyzing the repo path when automatic dependency resolution is skipped."
echo "The CUE expectation file is provided as a single file path."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/urllib3/urllib3.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/urllib3/urllib3/urllib3.json
EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/urllib3_PASS.cue
$RUN_MACARON_SCRIPT analyze -pe $EXPECTATION_FILE -rp https://github.com/urllib3/urllib3/urllib3 -b main -d 87a0ecee6e691fe5ff93cd000c0158deebef763b --skip-deps || log_fail

$COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "urllib3/urllib3: Analyzing the repo path when automatic dependency resolution is skipped."
echo "The CUE expectation file should be found via the directory path."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/urllib3/urllib3.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/urllib3/urllib3/urllib3.json
EXPECTATION_DIR=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/
$RUN_MACARON_SCRIPT analyze -pe $EXPECTATION_DIR -rp https://github.com/urllib3/urllib3/urllib3 -b main -d 87a0ecee6e691fe5ff93cd000c0158deebef763b --skip-deps || log_fail

$COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "slsa-framework/slsa-verifier: Analyzing the repo path when automatic dependency resolution is skipped"
echo "and CUE file is provided as expectation."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/slsa-verifier/slsa-verifier_cue_PASS.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/slsa-framework/slsa-verifier/slsa-verifier.json
EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/slsa_verifier_PASS.cue
$RUN_MACARON_SCRIPT analyze -pe $EXPECTATION_FILE -rp https://github.com/slsa-framework/slsa-verifier -b main -d fc50b662fcfeeeb0e97243554b47d9b20b14efac --skip-deps || log_fail

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

echo -e "\n----------------------------------------------------------------------------------"
echo "Test running the analysis without setting the GITHUB_TOKEN environment variables."
echo -e "----------------------------------------------------------------------------------\n"
temp="$GITHUB_TOKEN"
GITHUB_TOKEN="" && $RUN_MACARON_SCRIPT analyze -rp https://github.com/slsa-framework/slsa-verifier --skip-deps
if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi
GITHUB_TOKEN="$temp"

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: test analyzing with invalid PURL"
echo -e "----------------------------------------------------------------------------------\n"
$RUN_MACARON_SCRIPT analyze -purl invalid-purl -rp https://github.com/apache/maven --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: test analyzing with both PURL and repository path but no branch and digest are provided."
echo -e "----------------------------------------------------------------------------------\n"
$RUN_MACARON_SCRIPT analyze -purl pkg:maven/apache/maven -rp https://github.com/apache/maven --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

if [ $RESULT_CODE -ne 0 ];
then
    exit 1
fi
