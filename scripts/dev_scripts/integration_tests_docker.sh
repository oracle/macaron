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
echo "timyarkov/multibuild_test: Analyzing Maven artifact with the repo path, the branch name and the commit digest"
echo "with dependency resolution using cyclonedx Maven plugins (defaults)."
echo -e "----------------------------------------------------------------------------------\n"
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_timyarkov_multibuild_test_maven.json
DEP_RESULT=$WORKSPACE/output/reports/maven/org_example/mock_maven_proj/dependencies.json
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/maven/org.example/mock_maven_proj/1.0-SNAPSHOT/multibuild_test.dl
run_macaron_clean analyze -purl pkg:maven/org.example/mock_maven_proj@1.0-SNAPSHOT?type=jar -rp https://github.com/timyarkov/multibuild_test -b main -d a8b0efe24298bc81f63217aaa84776c3d48976c5 || log_fail

python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "timyarkov/multibuild_test: Analyzing Gradle artifact with the repo path, the branch name and the commit digest"
echo "with dependency resolution using cyclonedx Gradle plugins (defaults)."
echo -e "----------------------------------------------------------------------------------\n"
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_timyarkov_multibuild_test_gradle.json
DEP_RESULT=$WORKSPACE/output/reports/maven/org_example/mock_gradle_proj/dependencies.json
$RUN_MACARON_SCRIPT analyze -purl pkg:maven/org.example/mock_gradle_proj@1.0?type=jar -rp https://github.com/timyarkov/multibuild_test -b main -d a8b0efe24298bc81f63217aaa84776c3d48976c5 || log_fail

python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check the resolved dependency output with config for cyclonedx maven plugin (default)."
echo -e "----------------------------------------------------------------------------------\n"
DEP_RESULT=$WORKSPACE/output/reports/maven/org_apache_maven/maven/dependencies.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_apache_maven.json

run_macaron_clean analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/maven_config.yaml || log_fail
python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: e2e using the local repo path, the branch name and the commit digest without dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/maven/maven.dl

run_macaron_clean -lr $WORKSPACE/output/git_repos/github_com analyze -r apache/maven -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b --skip-deps || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check the e2e output JSON file with config and no dependency analyzing."
echo -e "----------------------------------------------------------------------------------\n"
EXPECT_DIR=$WORKSPACE/tests/e2e/expected_results/maven

declare -a COMPARE_FILES=(
    "maven.dl"
    "guava.dl"
    "mockito.dl"
)

run_macaron_clean analyze -c $WORKSPACE/tests/e2e/configurations/maven_config.yaml --skip-deps || log_fail

for i in "${COMPARE_FILES[@]}"
do
    $RUN_POLICY -d $DB -f $EXPECT_DIR/$i || log_fail
done

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing using a CycloneDx SBOM with target repo path"
echo -e "----------------------------------------------------------------------------------\n"
SBOM_FILE=$WORKSPACE/tests/dependency_analyzer/cyclonedx/resources/apache_maven_root_sbom.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/apache_maven_with_sbom_provided.json
DEP_RESULT=$WORKSPACE/output/reports/maven/org_apache_maven/maven/dependencies.json

run_macaron_clean analyze -purl pkg:maven/org.apache.maven/maven@4.0.0-alpha-1-SNAPSHOT?type=pom -rp https://github.com/apache/maven -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b -sbom "$SBOM_FILE" || log_fail

python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing with PURL and repository path without dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/purl/maven/maven.dl

run_macaron_clean analyze -purl pkg:maven/apache/maven -rp https://github.com/apache/maven -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b --skip-deps || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

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

echo -e "\n----------------------------------------------------------------------------------"
echo "urllib3/urllib3: Analyzing the repo path when automatic dependency resolution is skipped."
echo "The CUE expectation file should be found via the directory path."
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/urllib3/urllib3.dl
EXPECTATION_DIR=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/

run_macaron_clean analyze -pe $EXPECTATION_DIR -rp https://github.com/urllib3/urllib3/urllib3 -b main -d 87a0ecee6e691fe5ff93cd000c0158deebef763b --skip-deps || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "Test verifying CUE provenance expectation for ossf/scorecard"
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/scorecard/scorecard.dl
DEFAULTS_FILE=$WORKSPACE/tests/e2e/defaults/scorecard.ini
EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/scorecard_PASS.cue

run_macaron_clean -dp $DEFAULTS_FILE analyze -pe $EXPECTATION_FILE -purl pkg:github/ossf/scorecard@v4.13.1 --skip-deps || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "Run policy CLI with scorecard results."
echo -e "----------------------------------------------------------------------------------\n"
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/scorecard/scorecard.dl
POLICY_RESULT=$WORKSPACE/output/policy_report.json
POLICY_EXPECTED=$WORKSPACE/tests/policy_engine/expected_results/scorecard/scorecard_policy_report.json
VSA_RESULT=$WORKSPACE/output/vsa.intoto.jsonl
VSA_PAYLOAD_EXPECTED=$WORKSPACE/tests/vsa/integration/github_slsa-framework_scorecard/vsa_payload.json

$RUN_POLICY -f "$POLICY_FILE" -d $DB || log_fail
python $COMPARE_POLICIES $POLICY_RESULT $POLICY_EXPECTED || log_fail
python "$COMPARE_VSA" "$VSA_RESULT" "$VSA_PAYLOAD_EXPECTED" || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "slsa-framework/slsa-verifier: Analyzing the repo path when automatic dependency resolution is skipped"
echo "and CUE file is provided as expectation."
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/slsa-verifier/slsa-verifier_cue_PASS.dl
EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/slsa_verifier_PASS.cue
DEFAULTS_FILE=$WORKSPACE/tests/e2e/defaults/slsa_verifier.ini

run_macaron_clean -dp $DEFAULTS_FILE analyze -pe $EXPECTATION_FILE -rp https://github.com/slsa-framework/slsa-verifier -b main -d fc50b662fcfeeeb0e97243554b47d9b20b14efac --skip-deps || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "behnazh-w/example-maven-app as a local and remote repository"
echo "Test the Witness and GitHub provenances as an input, Cue expectation validation, Policy CLI and VSA generation."
echo -e "----------------------------------------------------------------------------------\n"
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/example-maven-project/policy.dl
POLICY_RESULT=$WORKSPACE/output/policy_report.json
POLICY_EXPECTED=$WORKSPACE/tests/policy_engine/expected_results/example-maven-project/example_maven_project_policy_report.json
VSA_RESULT=$WORKSPACE/output/vsa.intoto.jsonl
VSA_PAYLOAD_EXPECTED=$WORKSPACE/tests/vsa/integration/example-maven-project/vsa_payload.json

# Test the local repo with Witness provenance.
WITNESS_EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/witness-example-maven-project.cue
WITNESS_PROVENANCE_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/resources/valid_provenances/witness-example-maven-project.json

# Cloning the repository locally
git clone https://github.com/behnazh-w/example-maven-app.git $WORKSPACE/output/git_repos/local_repos/example-maven-app || log_fail

# Check the Witness provenance.
run_macaron_clean analyze -pf $WITNESS_PROVENANCE_FILE -pe $WITNESS_EXPECTATION_FILE -purl pkg:maven/io.github.behnazh-w.demo/example-maven-app@1.0-SNAPSHOT?type=jar --repo-path example-maven-app --skip-deps || log_fail

# Test the remote repo with GitHub provenance.
GITHUB_EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/github-example-maven-project.cue
GITHUB_PROVENANCE_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/resources/valid_provenances/github-example-maven-project.json

# Check the GitHub provenance.
$RUN_MACARON_SCRIPT analyze -pf $GITHUB_PROVENANCE_FILE -pe $GITHUB_EXPECTATION_FILE -purl pkg:maven/io.github.behnazh-w.demo/example-maven-app@1.0?type=jar --skip-deps || log_fail

# Verify the policy and VSA for all the software components generated from behnazh-w/example-maven-app repo.
$RUN_POLICY -f "$POLICY_FILE" -d $DB || log_fail

python "$COMPARE_POLICIES" "$POLICY_RESULT" "$POLICY_EXPECTED" || log_fail
python "$COMPARE_VSA" "$VSA_RESULT" "$VSA_PAYLOAD_EXPECTED" || log_fail

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

python3 ./tests/integration/run.py run \
    --macaron scripts/release_scripts/run_macaron.sh \
    --include-tag docker \
    ./tests/integration/cases/... || log_fail

if [ $RESULT_CODE -ne 0 ];
then
    exit 1
fi
