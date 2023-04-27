#!/bin/bash
# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script runs the integration tests using Macaron as a python package.

WORKSPACE=$1
HOMEDIR=$2
RESOURCES=$WORKSPACE/src/macaron/resources
COMPARE_DEPS=$WORKSPACE/tests/dependency_analyzer/compare_dependencies.py
COMPARE_JSON_OUT=$WORKSPACE/tests/e2e/compare_e2e_result.py
RUN_MACARON="python -m macaron -o $WORKSPACE/output -t $GITHUB_TOKEN"
RESULT_CODE=0

function log_fail() {
    printf "Error: FAILED integration test (line ${BASH_LINENO}) %s\n" $@
    RESULT_CODE=1
}


if [[ -z "${GITHUB_TOKEN}" ]]
then
  echo "Environment variable GITHUB_TOKEN not set."
  exit 1
fi

if [[ ! -d "$HOMEDIR/.m2/settings.xml" ]];
then
    if [[ ! -d "$HOMEDIR/.m2" ]];
    then
        mkdir -p $HOMEDIR/.m2
    fi
    cp $RESOURCES/settings.xml $HOMEDIR/.m2/
fi

# Running Macaron without config files
echo -e "\n=================================================================================="
echo "Run integration tests without configurations"
echo -e "==================================================================================\n"

echo -e "\n----------------------------------------------------------------------------------"
echo "micronaut-projects/micronaut-core: Analyzing the repo path and the branch name when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
$RUN_MACARON analyze -rp https://github.com/micronaut-projects/micronaut-core -b 3.5.x --skip-deps || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "jenkinsci/plot-plugin: Analyzing the repo path, the branch name and the commit digest when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/plot-plugin/plot-plugin.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/jenkinsci/plot-plugin/plot-plugin.json
$RUN_MACARON analyze -rp https://github.com/jenkinsci/plot-plugin -b master -d 55b059187e252b35ac0d6cb52268833ee1bb7380 --skip-deps || log_fail

python $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "urllib3/urllib3: Analyzing the repo path when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/urllib3/urllib3.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/urllib3/urllib3/urllib3.json
CUE_POLICY=$WORKSPACE/tests/policy_engine/resources/policies/valid/urllib3.cue
$RUN_MACARON -po $CUE_POLICY analyze -rp https://github.com/urllib3/urllib3/urllib3 -b main -d 87a0ecee6e691fe5ff93cd000c0158deebef763b --skip-deps || log_fail

python $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing the repo path, the branch name and the commit digest with dependency resolution using cyclonedx maven plugin (default)."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/maven/maven.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/maven.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_apache_maven.json
DEP_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/dependencies.json
$RUN_MACARON analyze -rp https://github.com/apache/maven -b master -d 6767f2500f1d005924ccff27f04350c253858a84 || log_fail

python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

python $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing the repo path, the branch name and the commit digest with dependency resolution using a CycloneDx SBOM."
echo -e "----------------------------------------------------------------------------------\n"
SBOM_FILE=$WORKSPACE/tests/dependency_analyzer/cyclonedx/resources/apache_maven_root_sbom.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/apache_maven_with_sbom_provided.json
DEP_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/dependencies.json

$RUN_MACARON analyze -rp https://github.com/apache/maven -b master -d 6767f2500f1d005924ccff27f04350c253858a84 -sbom "$SBOM_FILE" || log_fail

python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

# Analyze micronaut-projects/micronaut-core.
echo -e "\n=================================================================================="
echo "Run integration tests with configurations for micronaut-projects/micronaut-core..."
echo -e "==================================================================================\n"
DEP_RESULT=$WORKSPACE/output/reports/github_com/micronaut-projects/micronaut-core/dependencies.json

echo -e "\n----------------------------------------------------------------------------------"
echo "micronaut-projects/micronaut-core: Check the resolved dependency output when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/skipdep_micronaut-projects_micronaut-core.json
$RUN_MACARON analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/micronaut_core_config.yaml --skip-deps || log_fail

python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

# echo -e "\n----------------------------------------------------------------------------------"
# echo "micronaut-projects/micronaut-core: Check the resolved dependency output with config for cyclonedx gradle plugin (default)."
# echo -e "----------------------------------------------------------------------------------\n"
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_micronaut-projects_micronaut-core.json
$RUN_MACARON analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/micronaut_core_config.yaml || log_fail

# TODO: uncomment the test below after resolving https://github.com/oracle-samples/macaron/issues/60.
# python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "micronaut-projects/micronaut-core: Check the e2e output JSON file with config and no dependency analyzing."
echo -e "----------------------------------------------------------------------------------\n"
JSON_RESULT_DIR=$WORKSPACE/output/reports/github_com/micronaut-projects/micronaut-core/
JSON_EXPECT_DIR=$WORKSPACE/tests/e2e/expected_results/micronaut-core

declare -a COMPARE_FILES=(
    "micronaut-core.json"
    "caffeine.json"
    "slf4j.json"
)

$RUN_MACARON analyze -c $WORKSPACE/tests/e2e/configurations/micronaut_core_config.yaml --skip-deps || log_fail

for i in "${COMPARE_FILES[@]}"
do
    python $COMPARE_JSON_OUT $JSON_RESULT_DIR/$i $JSON_EXPECT_DIR/$i || log_fail
done

# Analyze apache/maven.
echo -e "\n=================================================================================="
echo "Run integration tests with configurations for apache/maven..."
echo -e "==================================================================================\n"
DEP_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/dependencies.json

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check the resolved dependency output when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/skipdep_apache_maven.json
$RUN_MACARON analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/maven_config.yaml --skip-deps || log_fail

python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

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

$RUN_MACARON analyze -c $WORKSPACE/tests/e2e/configurations/maven_config.yaml --skip-deps || log_fail

for i in "${COMPARE_FILES[@]}"
do
    python $COMPARE_JSON_OUT $JSON_RESULT_DIR/$i $JSON_EXPECT_DIR/$i || log_fail
done

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check the resolved dependency output with config for cyclonedx maven plugin."
echo -e "----------------------------------------------------------------------------------\n"
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_apache_maven.json
$RUN_MACARON analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/maven_config.yaml || log_fail

python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check: Check the e2e status code of running with invalid branch or digest defined in the yaml configuration."
echo -e "----------------------------------------------------------------------------------\n"
declare -a INVALID_BRANCH_DIGEST=(
    "maven_digest_no_branch.yaml"
    "maven_invalid_branch.yaml"
    "maven_invalid_digest.yaml"
)

for i in "${INVALID_BRANCH_DIGEST[@]}"
do
    echo -e "Running with $WORKSPACE/tests/e2e/configurations/$i"
    $RUN_MACARON analyze -c $WORKSPACE/tests/e2e/configurations/$i
    if [ $? -eq 0 ];
    then
        echo -e "Expect non-zero status code for $WORKSPACE/test/e2e/configurations/$i but got $?."
        log_fail
    fi
done

echo -e "\n----------------------------------------------------------------------------------"
echo "Test using the default template file."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/maven/maven.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/maven.json
$RUN_MACARON analyze -rp https://github.com/apache/maven --skip-deps -b master -d 6767f2500f1d005924ccff27f04350c253858a84 -g $WORKSPACE/src/macaron/output_reporter/templates/macaron.html || log_fail

python $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

# Analyze FasterXML/jackson-databind.
echo -e "\n=================================================================================="
echo "Run integration tests with configurations for FasterXML/jackson-databind..."
echo -e "==================================================================================\n"
JSON_RESULT=$WORKSPACE/output/reports/github_com/FasterXML/jackson-databind/jackson-databind.json

echo -e "\n----------------------------------------------------------------------------------"
echo "FasterXML/jackson-databind: Check the e2e output JSON file with config and no dependency analyzing."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/jackson-databind/jackson-databind.json
$RUN_MACARON analyze -c $WORKSPACE/tests/e2e/configurations/jackson_databind_config.yaml --skip-deps || log_fail

python $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

# echo -e "\n----------------------------------------------------------------------------------"
# echo "FasterXML/jackson-databind: Check the resolved dependency output with config for cyclonedx maven plugin (default)."
# echo -e "----------------------------------------------------------------------------------\n"
# DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_FasterXML_jackson-databind.json
# DEP_RESULT=$WORKSPACE/output/reports/github_com/FasterXML/jackson-databind/dependencies.json
# $RUN_MACARON analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/jackson_databind_config.yaml || log_fail

# python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

# Running Macaron using local paths.
echo -e "\n=================================================================================="
echo "Run integration tests with local paths for apache/maven..."
echo -e "==================================================================================\n"

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing with the branch name, the commit digest and dependency resolution using cyclonedx maven plugin (default)."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/maven/maven.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/maven.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_apache_maven.json
DEP_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/dependencies.json
$RUN_MACARON -lr $WORKSPACE/output/git_repos/github_com analyze -rp apache/maven -b master -d 6767f2500f1d005924ccff27f04350c253858a84 || log_fail

python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail
python $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing with local paths in configuration and without dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_RESULT_DIR=$WORKSPACE/output/reports/github_com/apache/maven
JSON_EXPECT_DIR=$WORKSPACE/tests/e2e/expected_results/maven

declare -a COMPARE_FILES=(
    "maven.json"
    "guava.json"
    "mockito.json"
)

$RUN_MACARON -lr $WORKSPACE/output/git_repos/github_com analyze -c $WORKSPACE/tests/e2e/configurations/maven_local_path.yaml --skip-deps || log_fail
for i in "${COMPARE_FILES[@]}"
do
    python $COMPARE_JSON_OUT $JSON_RESULT_DIR/$i $JSON_EXPECT_DIR/$i || log_fail
done

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing with local paths using local_repos_dir without dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
# The report files are still stored in the same location.
JSON_RESULT_DIR=$WORKSPACE/output/reports/github_com/apache/maven
JSON_EXPECT_DIR=$WORKSPACE/tests/e2e/expected_results/maven

declare -a COMPARE_FILES=(
    "maven.json"
    "guava.json"
    "mockito.json"
)

$RUN_MACARON -lr $WORKSPACE/output/git_repos/github_com/ analyze -rp apache/maven -b master -d 6767f2500f1d005924ccff27f04350c253858a84 --skip-deps || log_fail
for i in "${COMPARE_FILES[@]}"
do
    python $COMPARE_JSON_OUT $JSON_RESULT_DIR/$i $JSON_EXPECT_DIR/$i || log_fail
done

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing a repository that was cloned from another local repo."
echo -e "----------------------------------------------------------------------------------\n"
# Clone the repo from the existing apache/maven repo
rm -rf $WORKSPACE/output/git_repos/local_repos/test_repo
git clone $WORKSPACE/output/git_repos/github_com/apache/maven $WORKSPACE/output/git_repos/local_repos/test_repo

JSON_EXPECTED=$WORKSPACE/output/reports/local_repos/maven/maven.json
HTML_EXPECTED=$WORKSPACE/output/reports/local_repos/maven/maven.html

$RUN_MACARON -lr $WORKSPACE/output/git_repos/local_repos/ analyze -rp test_repo -b master -d 6767f2500f1d005924ccff27f04350c253858a84 --skip-deps || log_fail

# We don't compare the report content because the remote_path fields in the reports are undeterministic when running
# this test locally and running it in the GitHub Actions runner. We only check if the reports are generated as
# expected without the issue described in https://github.com/oracle-samples/macaron/issues/116.
ls $JSON_EXPECTED || log_fail
ls $HTML_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: test using invalid local repo path."
echo -e "----------------------------------------------------------------------------------\n"
# Assume that $WORKSPACE is always an absolute path.
$RUN_MACARON -lr $WORKSPACE/output/git_repos/github_com/ analyze -rp path/to/invalid/repo --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: test using invalid local_repos_dir."
echo -e "----------------------------------------------------------------------------------\n"
$RUN_MACARON -lr $WORKSPACE/invalid_dir_should_fail analyze -rp apache/maven --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: test using a repo path outside of local_repos_dir."
echo -e "----------------------------------------------------------------------------------\n"
$RUN_MACARON -lr $WORKSPACE/output/git_repos/github_com/ analyze -rp ../ --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "Test using local repo with no commits."
echo -e "----------------------------------------------------------------------------------\n"
mkdir -p $WORKSPACE/output/git_repos/local_repos/empty_repo
cd $WORKSPACE/output/git_repos/local_repos/empty_repo && git init && cd -
$RUN_MACARON -lr $WORKSPACE/output/git_repos/local_repos analyze -rp empty_repo --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: test not pulling from remote for a locally cloned repo."
echo -e "----------------------------------------------------------------------------------\n"
SOURCE_REPO="$WORKSPACE/output/git_repos/local_repos/source"
TARGET_REPO="$WORKSPACE/output/git_repos/local_repos/target"

mkdir -p  "$SOURCE_REPO"

# Prepare the first commit for the repository.
cd "$SOURCE_REPO" || log_fail
git init || log_fail
git config --local user.email "testing@example.com"
git config --local user.name "Testing"
echo 1 >> test1.txt || log_fail
git add test1.txt || log_fail
git commit -m "First commit" || log_fail

# Clone from SOURCE_REPO. TARGET_REPO will be identical to SOURCE_REPO and contain only the first commit.
mkdir -p "$TARGET_REPO"
git clone "$SOURCE_REPO" "$TARGET_REPO" || log_fail

# Create a second commit in SOURCE_REPO.
# Note that after this commit is created, TARGET_REPO will not have the second commit.
# However, because TARGET_REPO's remote origin points to SOURCE_REPO, the second commit can be pulled from SOURCE_REPO.
cd "$SOURCE_REPO" || log_fail
echo 2 >> test2.txt || log_fail
git add test2.txt || log_fail
git commit -m "Second commit"  || log_fail
# This is the SHA for the second commit, which exists in SOURCE_REPO but not in TARGET_REPO yet.
HEAD_COMMIT_SHA=$(git rev-parse HEAD) || log_fail

cd "$WORKSPACE"  || log_fail

# When we run the analysis, because we are providing a local repo path, Macaron is not supposed to pull the
# latest changes (i.e the second commit of SOURCE_REPO) into TARGET_REPO.
# Therefore, this analysis is expected to fail because the commit HEAD_COMMIT_SHA does not exist in TARGET_REPO.
$RUN_MACARON -lr $WORKSPACE/output/git_repos/local_repos/ analyze -rp target -b master -d "$HEAD_COMMIT_SHA" --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

# Clean up the repos.
rm -rf "$SOURCE_REPO"
rm -rf "$TARGET_REPO"

echo -e "\n----------------------------------------------------------------------------------"
echo "Test using a custom template file that does not exist."
echo -e "----------------------------------------------------------------------------------\n"
$RUN_MACARON analyze -rp https://github.com/apache/maven --skip-deps -g $WORKSPACE/should/not/exist

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "Test verifiying the SLSA provenance."
echo -e "----------------------------------------------------------------------------------\n"
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/slsa_verifier.yaml
PROV_FILE=$WORKSPACE/tests/policy_engine/resources/provenances/slsa-verifier-linux-amd64.intoto.jsonl
$RUN_MACARON -po $POLICY_FILE verify -pr $PROV_FILE || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "Test verifiying the SLSA provenance with invalid policy language."
echo -e "----------------------------------------------------------------------------------\n"
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/invalid.yaml
PROV_FILE=$WORKSPACE/tests/policy_engine/resources/provenances/slsa-verifier-linux-amd64.intoto.jsonl
$RUN_MACARON -po $POLICY_FILE verify -pr $PROV_FILE

if [ $? -eq 0 ];
then
    echo -e "Expected non-zero status code but got $?."
    log_fail
fi


# Testing the Souffle policy engine.
echo -e "\n----------------------------------------------------------------------------------"
echo "slsa-framework/slsa-verifier: Analyzing the repo path when automatic dependency resolution is skipped"
echo "and Datalog policy is provided."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/slsa-verifier/slsa-verifier.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/slsa-framework/slsa-verifier/slsa-verifier.json
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/valid/slsa-verifier.dl
$RUN_MACARON -po $POLICY_FILE analyze -rp https://github.com/slsa-framework/slsa-verifier -b main -d fc50b662fcfeeeb0e97243554b47d9b20b14efac --skip-deps || log_fail

python $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "Run policy CLI with slsa-verifier results."
echo -e "----------------------------------------------------------------------------------\n"
RUN_POLICY="policy_engine"
COMPARE_POLICIES=$WORKSPACE/tests/policy_engine/compare_policy_reports.py
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/valid/slsa-verifier.dl
POLICY_RESULT=$WORKSPACE/output/policy_report.json
POLICY_EXPECTED=$WORKSPACE/tests/policy_engine/expected_results/policy_report.json

# Run policy engine on the database and compare results.
$RUN_POLICY -f $POLICY_FILE -d "$WORKSPACE/output/macaron.db" || log_fail
python $COMPARE_POLICIES $POLICY_RESULT $POLICY_EXPECTED || log_fail

if [ $RESULT_CODE -ne 0 ];
then
    echo -e "Expected zero status code but got $RESULT_CODE."
    exit 1
fi
