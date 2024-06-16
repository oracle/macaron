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
echo "timyarkov/multibuild_test: Analyzing Maven artifact with the repo path, the branch name and the commit digest"
echo "with dependency resolution using cyclonedx Maven plugins (defaults)."
echo -e "----------------------------------------------------------------------------------\n"
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_timyarkov_multibuild_test_maven.json
DEP_RESULT=$WORKSPACE/output/reports/maven/org_example/mock_maven_proj/dependencies.json
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/maven/org.example/mock_maven_proj/1.0-SNAPSHOT/multibuild_test.dl

run_macaron_clean $ANALYZE -purl pkg:maven/org.example/mock_maven_proj@1.0-SNAPSHOT?type=jar -rp https://github.com/timyarkov/multibuild_test -b main -d a8b0efe24298bc81f63217aaa84776c3d48976c5 || log_fail
check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing the repo path, the branch name and the commit digest with dependency resolution using cyclonedx maven plugin (default)."
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/maven/org.apache.maven/maven/4.0.0-alpha-9-SNAPSHOT/maven.dl
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_apache_maven.json
DEP_RESULT=$WORKSPACE/output/reports/maven/org_apache_maven/maven/dependencies.json
run_macaron_clean $ANALYZE -purl pkg:maven/org.apache.maven/maven@4.0.0-alpha-9-SNAPSHOT?type=pom -rp https://github.com/apache/maven -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

# Analyze micronaut-projects/micronaut-test.
echo -e "\n=================================================================================="
echo "Run integration tests with configurations for micronaut-projects/micronaut-test..."
echo -e "==================================================================================\n"
DEP_RESULT=$WORKSPACE/output/reports/github_com/micronaut-projects/micronaut-test/dependencies.json

echo -e "\n----------------------------------------------------------------------------------"
echo "micronaut-projects/micronaut-test: Check the resolved dependency output when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/skipdep_micronaut-projects_micronaut-test.json
run_macaron_clean $ANALYZE -c $WORKSPACE/tests/dependency_analyzer/configurations/micronaut_test_config.yaml --skip-deps || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "micronaut-projects/micronaut-test: Check the e2e output JSON file with config when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
EXPECT_DIR=$WORKSPACE/tests/e2e/expected_results/micronaut-test

declare -a COMPARE_FILES=(
    "micronaut-test.dl"
    "caffeine.dl"
    "slf4j.dl"
)

for i in "${COMPARE_FILES[@]}"
do
    $RUN_POLICY -d $DB -f $EXPECT_DIR/$i || log_fail
done

# TODO: uncomment the test below after resolving https://github.com/oracle/macaron/issues/60.
# echo -e "\n----------------------------------------------------------------------------------"
# echo "micronaut-projects/micronaut-test: Check the resolved dependency output with config for cyclonedx gradle plugin (default)."
# echo -e "----------------------------------------------------------------------------------\n"
# DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_micronaut-projects_micronaut-test.dl
# run_macaron_clean analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/micronaut_test_config.yaml || log_fail

# python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

# Analyze apache/maven.
echo -e "\n=================================================================================="
echo "Run integration tests with configurations for apache/maven..."
echo -e "==================================================================================\n"

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check the resolved dependency output when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
DEP_RESULT=$WORKSPACE/output/reports/maven/org_apache_maven/maven/dependencies.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/skipdep_apache_maven.json
run_macaron_clean $ANALYZE -c $WORKSPACE/tests/dependency_analyzer/configurations/maven_config.yaml --skip-deps || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check: Check the e2e status code of running with invalid branch or digest defined in the yaml configuration."
echo -e "----------------------------------------------------------------------------------\n"
declare -a INVALID_BRANCH_DIGEST=(
    "maven_invalid_branch.yaml"
    "maven_invalid_digest.yaml"
)

for i in "${INVALID_BRANCH_DIGEST[@]}"
do
    echo -e "Running with $WORKSPACE/tests/e2e/configurations/$i"
    run_macaron_clean $ANALYZE -c $WORKSPACE/tests/e2e/configurations/$i
    if [ $? -eq 0 ];
    then
        echo -e "Expect non-zero status code for $WORKSPACE/test/e2e/configurations/$i but got $?."
        log_fail
    fi
done

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

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: test using a repo path outside of local_repos_dir."
echo -e "----------------------------------------------------------------------------------\n"
run_macaron_clean -lr $WORKSPACE/output/git_repos/github_com/ $ANALYZE -rp ../ --skip-deps

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
run_macaron_clean -lr $WORKSPACE/output/git_repos/local_repos $ANALYZE -rp empty_repo --skip-deps

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
run_macaron_clean -lr $WORKSPACE/output/git_repos/local_repos/ $ANALYZE -rp target -b master -d "$HEAD_COMMIT_SHA" --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

# Clean up the repos.
rm -rf "$SOURCE_REPO"
rm -rf "$TARGET_REPO"

echo -e "\n-----------------------------------------------------------------------------------------"
echo "pkg:pypi/django@5.0.6: Analyzing the dependencies with an invalid path to the virtual env dir."
echo -e "-----------------------------------------------------------------------------------------\n"
run_macaron_clean $ANALYZE -purl pkg:pypi/django@5.0.6 --python-venv invalid-path

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing dependencies when neither the repository nor SBOM is available."
echo -e "----------------------------------------------------------------------------------\n"
run_macaron_clean $ANALYZE -purl pkg:maven/private.apache.maven/maven@4.0.0-alpha-1-SNAPSHOT?type=pom || log_fail
# We expect the analysis to finish with no errors.

echo -e "\n----------------------------------------------------------------------------------"
echo "Test providing an invalid provenance file as input."
echo -e "----------------------------------------------------------------------------------\n"
run_macaron_clean $ANALYZE -rp https://github.com/apache/maven --provenance-file $WORKSPACE/golang/internal/cue_validator/resources/invalid_provenance.json --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "Test verifying CUE provenance expectation for slsa-verifier with explicitly-provided provenance file"
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/slsa-verifier/slsa-verifier_explicitly_provided_cue_PASS.dl
EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/slsa_verifier_PASS.cue
DEFAULTS_FILE=$WORKSPACE/tests/e2e/defaults/slsa_verifier.ini
PROVENANCE_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/resources/valid_provenances/slsa-verifier-linux-amd64.intoto.jsonl
run_macaron_clean -dp $DEFAULTS_FILE $ANALYZE -pe $EXPECTATION_FILE -pf $PROVENANCE_FILE -rp https://github.com/slsa-framework/slsa-verifier -d 6fb4f7e2dd9c2f5d4f55fa88f6796278a7bba6d6 --skip-deps || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "Test verifying CUE provenance expectation for slsa-verifier with explicitly-provided provenance file as a URL link file"
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/slsa-verifier/slsa-verifier_explicitly_provided_cue_PASS.dl
EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/slsa_verifier_PASS.cue
DEFAULTS_FILE=$WORKSPACE/tests/e2e/defaults/allow_url_link_github.ini
PROVENANCE_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/resources/valid_provenances/slsa-verifier-linux-amd64.intoto.jsonl
run_macaron_clean -dp $DEFAULTS_FILE $ANALYZE -pe $EXPECTATION_FILE -pf $PROVENANCE_FILE -rp https://github.com/slsa-framework/slsa-verifier -d 6fb4f7e2dd9c2f5d4f55fa88f6796278a7bba6d6 --skip-deps || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "urllib3/urllib3: Analyzing the repo path when automatic dependency resolution is skipped"
echo "and CUE file is provided as expectation."
echo -e "----------------------------------------------------------------------------------\n"
OUTPUT_POLICY=$WORKSPACE/tests/e2e/expected_results/urllib3/urllib3_cue_invalid.dl
EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/invalid_expectations/invalid.cue
run_macaron_clean $ANALYZE -pe $EXPECTATION_FILE -rp https://github.com/urllib3/urllib3 -b main -d 87a0ecee6e691fe5ff93cd000c0158deebef763b --skip-deps || log_fail

$RUN_POLICY -d $DB -f $OUTPUT_POLICY || log_fail

# Testing the Repo Finder's remote calls.
# This requires the 'packageurl' Python module
echo -e "\n----------------------------------------------------------------------------------"
echo "Testing Repo Finder functionality."
echo -e "----------------------------------------------------------------------------------\n"
check_or_update_expected_output $TEST_REPO_FINDER || log_fail
if [ $? -ne 0 ];
then
    echo -e "Expect zero status code but got $?."
    log_fail
fi

# Testing the Commit Finder's tag matching functionality.
echo -e "\n----------------------------------------------------------------------------------"
echo "Testing Commit Finder tag matching functionality."
echo -e "----------------------------------------------------------------------------------\n"
python $TEST_COMMIT_FINDER || log_fail
if [ $? -ne 0 ];
then
    echo -e "Expect zero status code but got $?."
    log_fail
fi

# This section includes integration tests that are provided as tutorials on the website.
echo -e "\n----------------------------------------------------------------------------------"
echo "Tutorial test for apache/maven: Analyzing using a CycloneDx SBOM file of a software component."
echo -e "----------------------------------------------------------------------------------\n"
SBOM_FILE=$WORKSPACE/docs/source/_static/examples/apache/maven/analyze_with_sbom/sbom.json
DEP_EXPECTED=$WORKSPACE/tests/tutorials/dependency_analyze/maven/org_apache_maven/maven/dependencies.json
DEP_RESULT=$WORKSPACE/output/reports/maven/org_apache_maven/maven/dependencies.json
run_macaron_clean $ANALYZE -purl pkg:maven/org.apache.maven/maven@3.9.7?type=pom -sbom "$SBOM_FILE" || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "Tutorial test for apache/maven: Analyzing using a CycloneDx SBOM file of a software component whose repository is not available."
echo -e "----------------------------------------------------------------------------------\n"
SBOM_FILE=$WORKSPACE/tests/tutorials/dependency_analyze/maven/private.apache.maven/maven/sbom.json
DEP_EXPECTED=$WORKSPACE/tests/tutorials/dependency_analyze/maven/private.apache.maven/maven/dependencies.json
DEP_RESULT=$WORKSPACE/output/reports/maven/private_apache_maven/maven/dependencies.json
run_macaron_clean $ANALYZE -purl pkg:maven/private.apache.maven/maven@4.0.0-alpha-1-SNAPSHOT?type=pom -sbom "$SBOM_FILE" || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "Tutorial test for pkg:pypi/django@5.0.6: Analyzing the dependencies with virtual env provided as input."
echo -e "----------------------------------------------------------------------------------\n"
# Prepare the virtual environment.
VIRTUAL_ENV_PATH=$WORKSPACE/.django_venv
$MAKE_VENV "$VIRTUAL_ENV_PATH"
"$VIRTUAL_ENV_PATH"/bin/pip install django==5.0.6
run_macaron_clean $ANALYZE -purl pkg:pypi/django@5.0.6 --python-venv "$VIRTUAL_ENV_PATH" || log_fail

# Check the dependencies using the policy engine.
RUN_POLICY="macaron verify-policy"
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/django/test_dependencies.dl
POLICY_RESULT=$WORKSPACE/output/policy_report.json
POLICY_EXPECTED=$WORKSPACE/tests/policy_engine/expected_results/django/test_dependencies.json

$RUN_POLICY -f "$POLICY_FILE" -d $DB || log_fail
check_or_update_expected_output $COMPARE_POLICIES "$POLICY_RESULT" "$POLICY_EXPECTED" || log_fail

# Clean up and remove the virtual environment.
rm -rf "$VIRTUAL_ENV_PATH"

echo -e "\n----------------------------------------------------------------------------------"
echo "Tutorial test for behnazh-w/example-maven-app: testing automatic dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
DEP_EXPECTED=$WORKSPACE/tests/tutorials/dependency_analyze/maven/io_github_behnazh-w_demo/example-maven-app/dependencies.json
DEP_RESULT=$WORKSPACE/output/reports/maven/io_github_behnazh-w_demo/example-maven-app/dependencies.json
run_macaron_clean $ANALYZE -purl pkg:maven/io.github.behnazh-w.demo/example-maven-app@1.0?type=jar -rp https://github.com/behnazh-w/example-maven-app || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

python3 ./tests/integration/run.py run \
    ./tests/integration/cases/... || log_fail

# Important: This should be at the end of the file
if [ $RESULT_CODE -ne 0 ];
then
    echo -e "Expected zero status code but got $RESULT_CODE."
    exit 1
fi
