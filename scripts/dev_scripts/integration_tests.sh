#!/bin/bash
# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script runs the integration tests using Macaron as a python package.

WORKSPACE=$1
HOMEDIR=$2
RESOURCES=$WORKSPACE/src/macaron/resources
COMPARE_DEPS=$WORKSPACE/tests/dependency_analyzer/compare_dependencies.py
COMPARE_JSON_OUT=$WORKSPACE/tests/e2e/compare_e2e_result.py
COMPARE_POLICIES=$WORKSPACE/tests/policy_engine/compare_policy_reports.py
COMPARE_VSA=$WORKSPACE/tests/vsa/compare_vsa.py
TEST_REPO_FINDER=$WORKSPACE/tests/e2e/repo_finder/repo_finder.py
TEST_COMMIT_FINDER=$WORKSPACE/tests/e2e/repo_finder/commit_finder.py
RUN_MACARON="python -m macaron -o $WORKSPACE/output"
RESULT_CODE=0
UPDATE=0

# Optional argument for updating the expected results.
if [ $# -eq 3 ] && [ "$3" == "--update" ] ; then
    echo "Updating the expected results to match those currently produced by Macaron."
    UPDATE=1
    COMPARE_VSA="$COMPARE_VSA --update"
fi

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
echo "micronaut-projects/micronaut-core: Analyzing the repo path and the branch name when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/micronaut-core/micronaut-core.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/micronaut-projects/micronaut-core/micronaut-core.json
$RUN_MACARON analyze -rp https://github.com/micronaut-projects/micronaut-core -b 3.8.x -d 68f9bb0a78fa930865d37fca39252b9ec66e4a43 --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

if [[ -z "$NO_NPM_TEST" ]]; then
    echo -e "\n----------------------------------------------------------------------------------"
    echo "sigstore/mock@0.1.0: Analyzing the PURL when automatic dependency resolution is skipped."
    echo -e "----------------------------------------------------------------------------------\n"
    JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/purl/npm/sigstore/mock/mock.json
    JSON_RESULT=$WORKSPACE/output/reports/npm/_sigstore/mock/mock.json
    $RUN_MACARON analyze -purl pkg:npm/@sigstore/mock@0.1.0 -rp https://github.com/sigstore/sigstore-js -b main -d ebdcfdfbdfeb9c9aeee6df53674ef230613629f5 --skip-deps || log_fail

    check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "gitlab.com/tinyMediaManager/tinyMediaManager: Analyzing the repo path and the branch name when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/tinyMediaManager/tinyMediaManager.json
JSON_RESULT=$WORKSPACE/output/reports/gitlab_com/tinyMediaManager/tinyMediaManager/tinyMediaManager.json
$RUN_MACARON analyze -rp https://gitlab.com/tinyMediaManager/tinyMediaManager -b main -d cca6b67a335074eca42136556f0a321f75dc4f48 --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "jenkinsci/plot-plugin: Analyzing the repo path, the branch name and the commit digest when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/plot-plugin/plot-plugin.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/jenkinsci/plot-plugin/plot-plugin.json
$RUN_MACARON analyze -rp https://github.com/jenkinsci/plot-plugin -b master -d 55b059187e252b35ac0d6cb52268833ee1bb7380 --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "urllib3/urllib3: Analyzing the repo path when automatic dependency resolution is skipped."
echo "The CUE expectation file is provided as a single file path."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/urllib3/urllib3.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/urllib3/urllib3/urllib3.json
EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/urllib3_PASS.cue
$RUN_MACARON analyze -pe $EXPECTATION_FILE -rp https://github.com/urllib3/urllib3/urllib3 -b main -d 87a0ecee6e691fe5ff93cd000c0158deebef763b --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "urllib3/urllib3: Analyzing the repo path when automatic dependency resolution is skipped."
echo "The CUE expectation file should be found via the directory path."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/urllib3/urllib3.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/urllib3/urllib3/urllib3.json
EXPECTATION_DIR=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/
$RUN_MACARON analyze -pe $EXPECTATION_DIR -rp https://github.com/urllib3/urllib3/urllib3 -b main -d 87a0ecee6e691fe5ff93cd000c0158deebef763b --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "timyarkov/multibuild_test: Analyzing the repo path, the branch name and the commit digest"
echo "with dependency resolution using cyclonedx Gradle and Maven plugins (defaults)."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/multibuild_test/multibuild_test.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/timyarkov/multibuild_test/multibuild_test.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_timyarkov_multibuild_test.json
DEP_RESULT=$WORKSPACE/output/reports/github_com/timyarkov/multibuild_test/dependencies.json
$RUN_MACARON analyze -rp https://github.com/timyarkov/multibuild_test -b main -d a8b0efe24298bc81f63217aaa84776c3d48976c5 || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo "timyarkov/docker_test: Analyzing the repo path, the branch name and the commit digest"
echo "when automatic dependency resolution is skipped, for a project using docker as a build tool."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/docker_test/docker_test.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/timyarkov/docker_test/docker_test.json
$RUN_MACARON analyze -rp https://github.com/timyarkov/docker_test -b main -d 404a51a2f38c4470af6b32e4e00b5318c2d7c0cc --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "uiv-lib/uiv: Analysing the repo path, the branch name and the commit digest for an npm project,"
echo "skipping dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/uiv/uiv.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/uiv-lib/uiv/uiv.json
$RUN_MACARON analyze -rp https://github.com/uiv-lib/uiv -b dev -d 057b25b4db0913edab4cf728c306085e6fc20d49 --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "onu-ui/onu-ui: Analysing the repo path, the branch name and the commit digest for a pnpm project,"
echo "skipping dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/onu-ui/onu-ui.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/onu-ui/onu-ui/onu-ui.json
$RUN_MACARON analyze -rp https://github.com/onu-ui/onu-ui -b main -d e3f2825c3940002a920d65476116a64684b3d95e --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "facebook/yoga: Analysing the repo path, the branch name and the commit digest for a Yarn classic"
echo "project, skipping dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/yoga/yoga.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/facebook/yoga/yoga.json
$RUN_MACARON analyze -rp https://github.com/facebook/yoga -b main -d f8e2bc0875c145c429d0e865c9b83a40f65b3070 --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "wojtekmaj/react-pdf: Analysing the repo path, the branch name and the commit digest for a Yarn modern"
echo "project, skipping dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/react-pdf/react-pdf.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/wojtekmaj/react-pdf/react-pdf.json
$RUN_MACARON analyze -rp https://github.com/wojtekmaj/react-pdf -b main -d be18436b7be827eb993b2e1e4bd9230dd835a9a3 --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "sigstore/sget: Analysing the repo path, the branch name and the"
echo "commit digest for a Go project, skipping dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/sget/sget.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/sigstore/sget/sget.json
$RUN_MACARON analyze -rp https://github.com/sigstore/sget -b main -d 99e7b91204d391ccc76507f7079b6d2a7957489e --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing with PURL and repository path without dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/purl/maven/maven.json
JSON_RESULT=$WORKSPACE/output/reports/maven/apache/maven/maven.json
$RUN_MACARON analyze -purl pkg:maven/apache/maven -rp https://github.com/apache/maven -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing the repo path, the branch name and the commit digest with dependency resolution using cyclonedx maven plugin (default)."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/maven/maven.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/maven.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_apache_maven.json
DEP_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/dependencies.json
$RUN_MACARON analyze -rp https://github.com/apache/maven -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing using a CycloneDx SBOM with target repo path"
echo -e "----------------------------------------------------------------------------------\n"
SBOM_FILE=$WORKSPACE/tests/dependency_analyzer/cyclonedx/resources/apache_maven_root_sbom.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/apache_maven_with_sbom_provided.json
DEP_RESULT=$WORKSPACE/output/reports/github_com/apache/maven/dependencies.json

$RUN_MACARON analyze -rp https://github.com/apache/maven -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b -sbom "$SBOM_FILE" || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail


echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing using a CycloneDx SBOM file of a software component whose repository is not available."
echo -e "----------------------------------------------------------------------------------\n"
SBOM_FILE=$WORKSPACE/tests/dependency_analyzer/cyclonedx/resources/private_mirror_apache_maven.json
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/private_mirror_apache_maven.json
DEP_RESULT=$WORKSPACE/output/reports/private_domain_com/apache/maven/dependencies.json

$RUN_MACARON analyze -purl pkg:private_domain.com/apache/maven -sbom "$SBOM_FILE" || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

# Analyze micronaut-projects/micronaut-test.
echo -e "\n=================================================================================="
echo "Run integration tests with configurations for micronaut-projects/micronaut-test..."
echo -e "==================================================================================\n"
DEP_RESULT=$WORKSPACE/output/reports/github_com/micronaut-projects/micronaut-test/dependencies.json

echo -e "\n----------------------------------------------------------------------------------"
echo "micronaut-projects/micronaut-test: Check the resolved dependency output when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/skipdep_micronaut-projects_micronaut-test.json
$RUN_MACARON analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/micronaut_test_config.yaml --skip-deps || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "micronaut-projects/micronaut-test: Check the e2e output JSON file with config when automatic dependency resolution is skipped."
echo -e "----------------------------------------------------------------------------------\n"
JSON_RESULT_DIR=$WORKSPACE/output/reports/github_com/micronaut-projects/micronaut-test/
JSON_EXPECT_DIR=$WORKSPACE/tests/e2e/expected_results/micronaut-test

declare -a COMPARE_FILES=(
    "micronaut-test.json"
    "caffeine.json"
    "slf4j.json"
)

for i in "${COMPARE_FILES[@]}"
do
    check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT_DIR/$i $JSON_EXPECT_DIR/$i || log_fail
done

# TODO: uncomment the test below after resolving https://github.com/oracle/macaron/issues/60.
# echo -e "\n----------------------------------------------------------------------------------"
# echo "micronaut-projects/micronaut-test: Check the resolved dependency output with config for cyclonedx gradle plugin (default)."
# echo -e "----------------------------------------------------------------------------------\n"
# DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_micronaut-projects_micronaut-test.json
# $RUN_MACARON analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/micronaut_test_config.yaml || log_fail

# python $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

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

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

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
    check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT_DIR/$i $JSON_EXPECT_DIR/$i || log_fail
done

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Check the resolved dependency output with config for cyclonedx maven plugin."
echo -e "----------------------------------------------------------------------------------\n"
DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_apache_maven.json
$RUN_MACARON analyze -c $WORKSPACE/tests/dependency_analyzer/configurations/maven_config.yaml || log_fail

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
$RUN_MACARON analyze -rp https://github.com/apache/maven --skip-deps -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b -g $WORKSPACE/src/macaron/output_reporter/templates/macaron.html || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

# Analyze FasterXML/jackson-databind.
echo -e "\n=================================================================================="
echo "Run integration tests with configurations for FasterXML/jackson-databind..."
echo -e "==================================================================================\n"
JSON_RESULT=$WORKSPACE/output/reports/maven/com_fasterxml_jackson_core/jackson-databind/jackson-databind.json

echo -e "\n----------------------------------------------------------------------------------"
echo "FasterXML/jackson-databind: Check the e2e output JSON file with config and no dependency analyzing."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/jackson-databind/jackson-databind.json
$RUN_MACARON analyze -purl pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.14.0-rc1 --skip-deps || log_fail
# Original commit f0af53d085eb2aa9f7f6199846cc526068e09977 seems to be first included in version tagged commit 2.14.0-rc1.

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

# echo -e "\n----------------------------------------------------------------------------------"
# echo "FasterXML/jackson-databind: Check the resolved dependency output with config for cyclonedx maven plugin (default)."
# echo -e "----------------------------------------------------------------------------------\n"
# DEP_EXPECTED=$WORKSPACE/tests/dependency_analyzer/expected_results/cyclonedx_FasterXML_jackson-databind.json
# DEP_RESULT=$WORKSPACE/output/reports/github_com/FasterXML/jackson-databind/dependencies.json
# $RUN_MACARON analyze -purl pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.14.0-rc1 || log_fail

# check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "google/guava: Analyzing with PURL and repository path without dependency resolution."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/purl/com_google_guava/guava/guava.json
JSON_RESULT=$WORKSPACE/output/reports/maven/com_google_guava/guava/guava.json
$RUN_MACARON analyze -purl pkg:maven/com.google.guava/guava@32.1.2-jre?type=jar --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail


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
$RUN_MACARON -lr $WORKSPACE/output/git_repos/github_com analyze -rp apache/maven -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b || log_fail

check_or_update_expected_output $COMPARE_DEPS $DEP_RESULT $DEP_EXPECTED || log_fail
check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

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
    check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT_DIR/$i $JSON_EXPECT_DIR/$i || log_fail
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

$RUN_MACARON -lr $WORKSPACE/output/git_repos/github_com/ analyze -rp apache/maven -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b --skip-deps || log_fail
for i in "${COMPARE_FILES[@]}"
do
    check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT_DIR/$i $JSON_EXPECT_DIR/$i || log_fail
done

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: Analyzing a repository that was cloned from another local repo."
echo -e "----------------------------------------------------------------------------------\n"
# Clone the repo from the existing apache/maven repo
rm -rf $WORKSPACE/output/git_repos/local_repos/test_repo
git clone $WORKSPACE/output/git_repos/github_com/apache/maven $WORKSPACE/output/git_repos/local_repos/test_repo

JSON_EXPECTED=$WORKSPACE/output/reports/local_repos/maven/maven.json
HTML_EXPECTED=$WORKSPACE/output/reports/local_repos/maven/maven.html

$RUN_MACARON -lr $WORKSPACE/output/git_repos/local_repos/ analyze -rp test_repo -b master -d 3fc399318edef0d5ba593723a24fff64291d6f9b --skip-deps || log_fail

# We don't compare the report content because the remote_path fields in the reports are nondeterministic when running
# this test locally and running it in the GitHub Actions runner. We only check if the reports are generated as
# expected without the issue described in https://github.com/oracle/macaron/issues/116.
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
echo "apache/maven: test analyzing without the environment variable GITHUB_TOKEN being set."
echo -e "----------------------------------------------------------------------------------\n"
temp="$GITHUB_TOKEN"
GITHUB_TOKEN="" && $RUN_MACARON analyze -rp https://github.com/apache/maven --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

GITHUB_TOKEN="$temp"

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: test analyzing with invalid PURL"
echo -e "----------------------------------------------------------------------------------\n"
$RUN_MACARON analyze -purl invalid-purl -rp https://github.com/apache/maven --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "apache/maven: test analyzing with both PURL and repository path but no branch and digest are provided."
echo -e "----------------------------------------------------------------------------------\n"
$RUN_MACARON analyze -purl pkg:maven/apache/maven -rp https://github.com/apache/maven --skip-deps

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

echo -e "\n----------------------------------------------------------------------------------"
echo "Test using a custom template file that does not exist."
echo -e "----------------------------------------------------------------------------------\n"
$RUN_MACARON analyze -rp https://github.com/apache/maven --skip-deps -g $WORKSPACE/should/not/exist

if [ $? -eq 0 ];
then
    echo -e "Expect non-zero status code but got $?."
    log_fail
fi

# Testing the CUE provenance expectation verifier.
echo -e "\n----------------------------------------------------------------------------------"
echo "Test verifying CUE provenance expectation."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/slsa-verifier/slsa-verifier_cue_PASS.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/slsa-framework/slsa-verifier/slsa-verifier.json
EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/valid_expectations/slsa_verifier_PASS.cue
$RUN_MACARON analyze -pe $EXPECTATION_FILE -rp https://github.com/slsa-framework/slsa-verifier -b main -d fc50b662fcfeeeb0e97243554b47d9b20b14efac --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

echo -e "\n----------------------------------------------------------------------------------"
echo "urllib3/urllib3: Analyzing the repo path when automatic dependency resolution is skipped"
echo "and CUE file is provided as expectation."
echo -e "----------------------------------------------------------------------------------\n"
JSON_EXPECTED=$WORKSPACE/tests/e2e/expected_results/urllib3/urllib3_cue_invalid.json
JSON_RESULT=$WORKSPACE/output/reports/github_com/urllib3/urllib3/urllib3.json
EXPECTATION_FILE=$WORKSPACE/tests/slsa_analyzer/provenance/expectations/cue/resources/invalid_expectations/invalid.cue
$RUN_MACARON analyze -pe $EXPECTATION_FILE -rp https://github.com/urllib3/urllib3 -b main -d 87a0ecee6e691fe5ff93cd000c0158deebef763b --skip-deps || log_fail

check_or_update_expected_output $COMPARE_JSON_OUT $JSON_RESULT $JSON_EXPECTED || log_fail

# Testing the Souffle policy engine.
echo -e "\n----------------------------------------------------------------------------------"
echo "Run policy CLI with slsa-verifier results."
echo -e "----------------------------------------------------------------------------------\n"
RUN_POLICY="macaron verify-policy"
POLICY_FILE=$WORKSPACE/tests/policy_engine/resources/policies/valid/slsa-verifier.dl
POLICY_RESULT=$WORKSPACE/output/policy_report.json
POLICY_EXPECTED=$WORKSPACE/tests/policy_engine/expected_results/policy_report.json
VSA_RESULT=$WORKSPACE/output/vsa.intoto.jsonl
VSA_PAYLOAD_EXPECTED=$WORKSPACE/tests/vsa/integration/github_slsa-framework_slsa-verifier/vsa_payload.json

# Run policy engine on the database and compare results.
$RUN_POLICY -f $POLICY_FILE -d "$WORKSPACE/output/macaron.db" || log_fail
check_or_update_expected_output $COMPARE_POLICIES $POLICY_RESULT $POLICY_EXPECTED || log_fail
check_or_update_expected_output "$COMPARE_VSA" "$VSA_RESULT" "$VSA_PAYLOAD_EXPECTED" || log_fail

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

# Important: This should be at the end of the file
if [ $RESULT_CODE -ne 0 ];
then
    echo -e "Expected zero status code but got $RESULT_CODE."
    exit 1
fi
