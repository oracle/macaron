#!/bin/bash
# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script runs the integration tests using Macaron as a python package.

WORKSPACE=$1
HOMEDIR=$2
RESOURCES=$WORKSPACE/src/macaron/resources
COMPARE_POLICIES=$WORKSPACE/tests/policy_engine/compare_policy_reports.py
COMPARE_VSA=$WORKSPACE/tests/vsa/compare_vsa.py
TEST_REPO_FINDER=$WORKSPACE/tests/e2e/repo_finder/repo_finder.py
TEST_COMMIT_FINDER=$WORKSPACE/tests/e2e/repo_finder/commit_finder.py
DB=$WORKSPACE/output/macaron.db
RUN_MACARON="python -m macaron -o $WORKSPACE/output"
ANALYZE="analyze"
RUN_POLICY="python -m macaron verify-policy"
MAKE_VENV="python -m venv"
RESULT_CODE=0
UPDATE=0

# Optional argument for updating the expected results.
if [ $# -eq 3 ] && [ "$3" == "--update" ] ; then
    echo "Updating the expected results to match those currently produced by Macaron."
    UPDATE=1
    COMPARE_VSA="$COMPARE_VSA --update"
fi

function run_macaron_clean() {
    rm $DB
    $RUN_MACARON "$@"
}

function check_or_update_expected_output() {
    if [ $UPDATE -eq 1 ] ; then
        # Perform update of expected results.
        # The update only takes place if sufficient arguments are present.
        # This function assumes:
        # - argument #1 is the path to the compare script.
        # - arguments #2 and #3 are files: <actual_result>, <expected_result>.
        if [ $# -eq 3 ] ; then
            compare_script_name=$(basename "$1")
            case "$compare_script_name" in
                # For scripts having an `--update` flag, use it.
                compare_vsa.py)
                  python "$1" --update "$2" "$3"
                  ;;
                # For the other scripts, copy over the produced output files.
                *)
                  echo "Copying $2 to $3"
                  cp "$2" "$3"
                  ;;
            esac
        else
            # Calls with insufficient arguments are ignored to avoid some needless computation during updates.
            echo "Ignoring" "$@"
        fi
    else
        # Perform normal operation.
        python "$@"
    fi
}

# Check if npm-related tests should be disabled.
if [[ "$NO_NPM" == "TRUE" ]]; then
    echo "Note: NO_NPM environment variable is set to TRUE, so npm tests will be skipped."
fi
NO_NPM_TEST=$NO_NPM

function log_fail() {
    printf "Error: FAILED integration test (line ${BASH_LINENO}) %s\n" $@
    RESULT_CODE=1
}

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
echo "apache/maven: Analyzing the repo path, the branch name and the commit digest with dependency resolution using cyclonedx maven plugin (default)."
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/maven/org.apache.maven/maven/4.0.0-alpha-9-SNAPSHOT/maven.dl
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_apache_maven.json
DEP_RESULT=$WORKSPACE/output/reports/maven/org_apache_maven/maven/dependencies.json
run_macaron_clean $ANALYZE -purl pkg:maven/org.apache.maven/maven@4.0.0-alpha-9-SNAPSHOT?type=pom -rp https://github.com/apache/maven -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

# TODO: uncomment the test below after resolving https://github.com/oracle/macaron/issues/60.
# echo -e "\n----------------------------------------------------------------------------------"
# echo "micronaut-projects/micronaut-test: Check the resolved dependency output with config for cyclonedx gradle plugin (default)."
# echo -e "----------------------------------------------------------------------------------\n"
# DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_micronaut-projects_micronaut-test.dl
# run_macaron_clean analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/micronaut_test_config.yaml || log_fail

# python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "Test using the default template file."
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/maven/maven.dl
run_macaron_clean $ANALYZE -rp https://github.com/apache/maven --skip-deps -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b -g $WORKSPACE/src/macaron/output_reporter/templates/macaron.html || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

# Analyze FasterXML/jackson-databind.
echo -e "\n=================================================================================="
echo "Run integration tests with configurations for FasterXML/jackson-databind..."
echo -e "==================================================================================\n"

echo -e "\n----------------------------------------------------------------------------------"
echo "FasterXML/jackson-databind: Check the e2e output JSON file with config and no dependency analyzing."
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/jackson-databind/jackson-databind.dl
run_macaron_clean $ANALYZE -purl pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.14.0-rc1 --skip-deps || log_fail
# Original commit f0af53d085eb2aa9f7f6199846cc526068e09977 seems to be first included in version tagged commit 2.14.0-rc1.

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

# echo -e "\n----------------------------------------------------------------------------------"
# echo "FasterXML/jackson-databind: Check the resolved dependency output with config for cyclonedx maven plugin (default)."
# echo -e "----------------------------------------------------------------------------------\n"
# DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_FasterXML_jackson-databind.json
# DEP_RESULT=$WORKSPACE/output/reports/github_com/FasterXML/jackson-databind/dependencies.json
# run_macaron_clean $ANALYZE -purl pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.14.0-rc1 || log_fail

# check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

# Running Macaron using local paths.
echo -e "\n=================================================================================="
echo "Run integration tests with local paths for apache/maven..."
echo -e "==================================================================================\n"

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing local clone with the branch name, the commit digest and dependency resolution using cyclonedx maven plugin (default)."
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/maven/org.apache.maven/maven/4.0.0-alpha-9-SNAPSHOT/maven.dl
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_apache_maven.json
DEP_RESULT=$WORKSPACE/output/reports/maven/org_apache_maven/maven/dependencies.json
run_macaron_clean -lr $WORKSPACE/output/git_repos/github_com $ANALYZE -purl pkg:maven/org.apache.maven/maven@4.0.0-alpha-9-SNAPSHOT?type=pom -rp apache/maven -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail
$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing with local paths in configuration and without dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
EXPECT_DIR=$WORKSPACE/tests/e2e/expected_results/maven

declare -a COMPARE_FILES=(
    "maven.dl"
    "guava.dl"
    "mockito.dl"
)

run_macaron_clean -lr $WORKSPACE/output/git_repos/github_com $ANALYZE -c $WORKSPACE/tests/e2e/configurations/maven_local_path.yaml --skip-deps || log_fail
for i in "${COMPARE_FILES[@]}"
do
    $RUN_POLICY -d $DB -f $EXPECT_DIR/$i || log_fail
done

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing a repository that was cloned from another local repo."
echo -e "----------------------------------------------------------------------------------\n"
# Clone the repo from the existing apache/maven repo
rm -rf $WORKSPACE/output/git_repos/local_repos/test_repo
git clone $WORKSPACE/output/git_repos/github_com/apache/maven $WORKSPACE/output/git_repos/local_repos/test_repo

JSON_EXPECTED=$WORKSPACE/output/reports/local_repos/maven/maven.json
HTML_EXPECTED=$WORKSPACE/output/reports/local_repos/maven/maven.html

run_macaron_clean -lr $WORKSPACE/output/git_repos/local_repos/ $ANALYZE -rp test_repo -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b --skip-deps || log_fail

# We don't compare the report content because the remote_path fields in the reports are nondeterministic when running
# this test locally and running it in the GitHub Actions runner. We only check if the reports are generated as
# expected without the issue described in https://github.com/oracle/macaron/issues/116.
ls $JSON_EXPECTED || log_fail
ls $HTML_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: test using invalid local repo path."
echo -e "----------------------------------------------------------------------------------\n"
# Assume that $WORKSPACE is always an absolute path.
run_macaron_clean -lr $WORKSPACE/output/git_repos/github_com/ $ANALYZE -rp path/to/invalid/repo --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: test using invalid local_repos_dir."
echo -e "----------------------------------------------------------------------------------\n"
run_macaron_clean -lr $WORKSPACE/invalid_dir_should_fail $ANALYZE -rp apache/maven --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

python ./tests/integration/run.py run \
    --exclude-tag docker-only \
    ./tests/integration/cases/... || log_fail

# Important: This should be at the end of the file
if [ $RESULT_CODE -ne 0 ];
then
    echo -e "Expected zero status code but got $RESULT_CODE."
    exit 1
fi
