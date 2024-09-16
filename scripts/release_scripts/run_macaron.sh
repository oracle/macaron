#!/usr/bin/env bash

# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script runs the Macaron Docker image.

# Strict bash options.
#
# -e:          exit immediately if a command fails (with non-zero return code),
#              or if a function returns non-zero.
#
# -u:          treat unset variables and parameters as error when performing
#              parameter expansion.
#              In case a variable ${VAR} is unset but we still need to expand,
#              use the syntax ${VAR:-} to expand it to an empty string.
#
# -o pipefail: set the return value of a pipeline to the value of the last
#              (rightmost) command to exit with a non-zero status, or zero
#              if all commands in the pipeline exit successfully.
#
# Reference: https://www.gnu.org/software/bash/manual/html_node/The-Set-Builtin.html.
set -euo pipefail

# The `extglob` shopt option is required for the `@(...)` pattern matching syntax.
# This option is not enabled by default for bash on some systems, most notably macOS
# where the default bash version is very old.
# Reference: https://www.gnu.org/software/bash/manual/html_node/The-Shopt-Builtin.html
shopt -s extglob

# Log error (to stderr).
log_err() {
    echo "[ERROR]: $*" >&2
}

# Log warning (to stderr).
log_warning() {
    echo "[WARNING]: $*" >&2
}

if [[ "${BASH_VERSINFO[0]}" -lt "4" ]]; then
    log_warning "Your bash version, '${BASH_VERSION}', is too old and is not actively supported by Macaron."
    log_warning "Using bash version >=4 is recommended."
fi

# Determine the Macaron image tag.
if [[ -z ${MACARON_IMAGE_TAG:-} ]]; then
    MACARON_IMAGE_TAG="latest"
fi

# This file is used to store token environment variables that will later be read by Macaron.
TOKEN_FILE=".macaron_env_file"

IMAGE="ghcr.io/oracle/macaron"

# Workspace directory inside of the container.
MACARON_WORKSPACE="/home/macaron"

# The entrypoint to run Macaron or the Policy Engine.
# It it set by default to macaron.
# We use an array here to preserve the arguments as provided by the user.
entrypoint=()

# The `macaron` command to execute (e.g. `analyze`, or `verify-policy`)
command=""

# `argv_main` and `argv_command` are arguments whose values changed by this script.
# `argv_main` are arguments of the `macaron` command.
# `argv_command` are arguments of the commands in `macaron` (e.g. `analyze`, or `verify-policy`).
argv_main=()
argv_command=()

# `rest_main` and `rest_command` are arguments whose values are not changed by this script.
# `rest_main` are arguments of the `macaron` command.
# `rest_command` are arguments of the commands in `macaron` (e.g. `analyze`, or `verify-policy`).
rest_main=()
rest_command=()

# The mounted directories/files from the host machine to the runtime Macaron container.
mounts=()

# The proxy values obtained from the host environment.
proxy_vars=()

# Convert a path to absolute path if it is a relative path.
#
# Arguments:
#   $1: The path.
# Outputs:
#   STDOUT: The absolute path.
function to_absolute_path() {
    if [[ "$1" != /* ]]; then
        echo "$(pwd)/$1"
    else
        echo "$1"
    fi
}

# Assert that a directory exists.
# This method is important since we want to ensure that all docker mounts works
# properly. If we mount a non-existing host directory into the container, docker
# creates an empty directory owned by root, which is not what we really want.
#
# Arguments:
#   $1: The path to the directory.
#   $2: The macaron argument from which the directory is passed into this script.
#
# With the `set -e` option turned on, this function exits the script with
# return code 1 if the directory does not exist.
function assert_dir_exists() {
    path=$1
    arg_name=$2
    if [[ ! -d "$path" ]]; then
        if [[ -z "${arg_name:-}" ]]; then
            log_err "Directory $path does not exist."
        else
            log_err "Directory $path of argument $arg_name does not exist."
        fi
        return 1
    fi
}

# Assert that a file exists.
#
# Arguments:
#   $1: The path to the file.
#   $2: The macaron argument from which the file is passed into this script.
#
# With the `set -e` option turned on, this function exits the script with
# return code 1 if the file does not exist.
function assert_file_exists() {
    if [[ ! -f "$1" ]]; then
        log_err "File $1 of argument $2 does not exist."
        return 1
    fi
}

# Assert that a path exists.
#
# Arguments:
#   $1: The path to a file or directory.
#   $2: The macaron argument from which the path is passed into this script.
#
# With the `set -e` option turned on, this function exits the script with
# return code 1 if the path does not exist.
function assert_path_exists() {
    if [[ ! -s "$1" ]]; then
        log_err "File $1 of argument $2 is neither file nor directory."
        return 1
    fi
}

# Create a directory if it does not exist.
# Arguments:
#   $1: The directory to create.
function create_dir_if_not_exists() {
    dir=$1
    if [ ! -d "$dir" ]; then
        # Use the `-p` option for `mkdir` intead of `--parents` to be compatible with macOS.
        mkdir -p "$dir"
    fi
}

# Add a directory to the list of volume mounts stored in the ``mounts`` global variable.
# Note: Do not use this function directly for mounting directories.
# Use one among these instead: `mount_dir_ro`, `mount_dir_rw_allow_create`, or
# `mount_dir_rw_forbid_create` instead.
#
# Arguments:
#   $1: The macaron argument from which the directory is passed into this script.
#   $2: The path to the directory on the host.
#   $3: The path to the directory inside the container.
#   $4: Mount option. Note: this MUST be either `ro,Z` for readonly volume mounts,
#       or `rw,Z` otherwise.
function _mount_dir() {
    arg_name=$1
    dir_on_host=$2
    dir_in_container=$3
    mount_option=$4

    dir_on_host=$(to_absolute_path "$dir_on_host")
    mounts+=("-v" "${dir_on_host}:${dir_in_container}:${mount_option}")
}

# Add a directory to the list of volume mounts stored in the ``mounts`` global variable,
# with the `ro,Z` mount option.
# If the mounted directory does not exist on the host, this function errors
# and exits the script.
#
# Arguments:
#   $1: The macaron argument from which the directory is passed into this script.
#   $2: The path to the directory on the host.
#   $3: The path to the directory inside the container.
function mount_dir_ro() {
    arg_name=$1
    dir_on_host=$2
    dir_in_container=$3

    assert_dir_exists "$dir_on_host" "$arg_name"
    _mount_dir "$arg_name" "$dir_on_host" "$dir_in_container" "ro,Z"
}

# Add a directory to the list of volume mounts stored in the ``mounts`` global variable,
# with the `rw,Z` mount option.
# If the mounted directory does not exist on the host, this function creates
# that directory before mounting.
# Note: This function ensures compatibility with podman, as podman does not
# create the directory on host if it does not exist and instead errors on mount.
#
# Arguments:
#   $1: The macaron argument from which the directory is passed into this script.
#   $2: The path to the directory on the host.
#   $3: The path to the directory inside the container.
function mount_dir_rw_allow_create() {
    arg_name=$1
    dir_on_host=$2
    dir_in_container=$3

    create_dir_if_not_exists "$dir_on_host"
    _mount_dir "$arg_name" "$dir_on_host" "$dir_in_container" "rw,Z"
}

# Add a directory to the list of volume mounts stored in the ``mounts`` global variable,
# with the `rw,Z` mount option.
# If the mounted directory does not exist on the host, this function errors and
# exits the script.
# Note: This function ensures compatibility with podman, as podman does not
# create the directory on host if it does not exist and instead errors on mount.
#
# Arguments:
#   $1: The macaron argument from which the directory is passed into this script.
#   $2: The path to the directory on the host.
#   $3: The path to the directory inside the container.
function mount_dir_rw_forbid_create() {
    arg_name=$1
    dir_on_host=$2
    dir_in_container=$3

    assert_dir_exists "$dir_on_host" "$arg_name"
    _mount_dir "$arg_name" "$dir_on_host" "$dir_in_container" "rw,Z"
}

# Add a file to the list of volume mounts stored in the ``mounts`` global variable.
#
# Arguments:
#   $1: The macaron argument from which the file is passed into this script.
#   $2: The path to the file on the host.
#   $3: The path to the file inside the container.
#   $4: Mount option. Note: this MUST be either `ro,Z` for readonly volumes,
#       or `rw,Z` otherwise.
function mount_file() {
    arg_name=$1
    file_on_host=$2
    file_in_container=$3
    mount_option=$4

    assert_file_exists "$file_on_host" "$arg_name"
    file_on_host=$(to_absolute_path "$file_on_host")
    mounts+=("-v" "${file_on_host}:${file_in_container}:${mount_option}")
}

# Clean up the token file and EXIT this bash script with the given status code.
#
# Arguments:
#   $1: The eventual exit status code.
#   $2: The path to the token file.
function clean_up_exit() {
    status_code=$1
    token_file_path=$2
    rm -f "$token_file_path"
    exit "$status_code"
}

# Parse main arguments.
while [[ $# -gt 0 ]]; do
    case $1 in
        # Parsing entry points.
        macaron)
            entrypoint+=("macaron")
            ;;
        # Parsing commands for macaron entrypoint.
        analyze|dump-defaults|verify-policy)
            command=$1
            shift
            break
            ;;
        # Main argv for main in macaron entrypoint.
        -dp|--defaults-path)
            arg_defaults_path="$2"
            shift
            ;;
        -o|--output)
            arg_output="$2"
            shift
            ;;
        -lr|--local-repos-path)
            arg_local_repos_path="$2"
            shift
            ;;
        *) # Pass the rest to Macaron.
            rest_main+=("$1")
            ;;
    esac
    shift
done

# Parse command-specific arguments.
if [[ $command == "analyze" ]]; then
    while [[ $# -gt 0 ]]; do
        case $1 in
            -sbom|--sbom-path)
                arg_sbom_path="$2"
                shift
                ;;
            -pe|--provenance-expectation)
                arg_prov_exp="$2"
                shift
                ;;
            -pf|--provenance-file)
                arg_prov_file="$2"
                shift
                ;;
            -g|--template-path)
                arg_template_path="$2"
                shift
                ;;
            --python-venv)
                python_venv_path="$2"
                shift
                ;;
            *)
                rest_command+=("$1")
                ;;
        esac
        shift
    done
elif [[ $command == "verify-policy" ]]; then
     while [[ $# -gt 0 ]]; do
        case $1 in
            -d|--database)
                arg_database="$2"
                shift
                ;;
            -f|--file)
                arg_datalog_policy_file="$2"
                shift
                ;;
            *)
                rest_command+=("$1")
                ;;
        esac
        shift
    done
fi

# MACARON entrypoint - Main argvs
# Determine the output path to be mounted into ${MACARON_WORKSPACE}/output/
if [[ -n "${arg_output:-}" ]]; then
    output="${arg_output}"
    argv_main+=("--output" "${MACARON_WORKSPACE}/output/")
else
    output=$(pwd)/output
    echo "Setting default output directory to ${output}."
fi

# Mount the necessary .m2 and .gradle directories.
m2_dir="${output}/.m2"
gradle_dir="${output}/.gradle"

mount_dir_rw_allow_create "" "$output" "${MACARON_WORKSPACE}/output"
mount_dir_rw_allow_create "" "$m2_dir" "${MACARON_WORKSPACE}/.m2"
mount_dir_rw_allow_create "" "$gradle_dir" "${MACARON_WORKSPACE}/.gradle"

# Determine the local repos path to be mounted into ${MACARON_WORKSPACE}/output/git_repos/local_repos/
if [[ -n "${arg_local_repos_path:-}" ]]; then
    local_repo_path_in_container="${MACARON_WORKSPACE}/output/git_repos/local_repos"

    argv_main+=("--local-repos-path" "$local_repo_path_in_container")
    mount_dir_rw_allow_create "-lr/--local-repos-path" "$arg_local_repos_path" "$local_repo_path_in_container"
fi

# Determine the defaults path to be mounted into ${MACARON_WORKSPACE}/defaults/${file_name}
if [[ -n "${arg_defaults_path:-}" ]]; then
    defaults_path="${arg_defaults_path}"
    file_name="$(basename "${arg_defaults_path}")"
    defaults_path_in_container="${MACARON_WORKSPACE}/defaults/${file_name}"

    argv_main+=("--defaults-path" "$defaults_path_in_container")
    mount_file "-dp/--defaults-path" "$defaults_path" "$defaults_path_in_container" "ro,Z"
fi

# Determine the policy path to be mounted into ${MACARON_WORKSPACE}/policy/${file_name}
if [[ -n "${arg_policy:-}" ]]; then
    policy_file="${arg_policy}"
    file_name="$(basename "${policy_file}")"
    policy_file_in_container="${MACARON_WORKSPACE}/policy/${file_name}"

    argv_main+=("--policy" "$policy_file_in_container")
    mount_file "-po/--policy" "$policy_file" "$policy_file_in_container" "ro,Z"
fi

# MACARON entrypoint - Analyze command argvs
# Determine the template path to be mounted into ${MACARON_WORKSPACE}/template/${file_name}
if [[ -n "${arg_template_path:-}" ]]; then
    template_path="${arg_template_path}"
    file_name="$(basename "${template_path}")"
    template_path_in_container="${MACARON_WORKSPACE}/template/${file_name}"

    argv_command+=("--template-path" "$template_path_in_container")
    mount_file "-g/--template-path" "$template_path" "$template_path_in_container" "ro,Z"
fi

# Determine the sbom path to be mounted into ${MACARON_WORKSPACE}/sbom/${file_name}
if [[ -n "${arg_sbom_path:-}" ]]; then
    sbom_path="${arg_sbom_path}"
    file_name="$(basename "${sbom_path}")"
    sbom_path_in_container="${MACARON_WORKSPACE}/sbom/${file_name}"

    argv_command+=("--sbom-path" "$sbom_path_in_container")
    mount_file "-sbom/--sbom-path" "$sbom_path" "$sbom_path_in_container" "ro,Z"
fi

# Determine the provenance expectation path to be mounted into ${MACARON_WORKSPACE}/prov_expectations/${pe_name} where pe_name can either be a directory or a file
if [[ -n "${arg_prov_exp:-}" ]]; then
    prov_exp_path="${arg_prov_exp}"
    assert_path_exists "${prov_exp_path}" "-pe/--provenance-expectation"
    prov_exp_name="$(basename "${prov_exp_path}")"
    prov_exp_path_in_container=${MACARON_WORKSPACE}/prov_expectations/${prov_exp_name}
    argv_command+=("--provenance-expectation" "$prov_exp_path_in_container")

    if [ -d "$prov_exp_path" ]; then
        mount_dir_ro "-pe/--provenance-expectation" "$prov_exp_path" "$prov_exp_path_in_container"
    elif [ -f "$prov_exp_path" ]; then
        mount_file "-pe/--provenance-expectation" "$prov_exp_path" "$prov_exp_path_in_container" "ro,Z"
    fi
fi

# Mount the provenance file into ${MACARON_WORKSPACE}/prov_files/${pf_name} where pf_name is a file name.
if [[ -n "${arg_prov_file:-}" ]]; then
    prov_file_path="${arg_prov_file}"
    prov_file_name="$(basename "${prov_file_path}")"
    prov_file_path_in_container=${MACARON_WORKSPACE}/prov_files/${prov_file_name}
    argv_command+=("--provenance-file" "$prov_file_path_in_container")

    mount_file "-pf/--provenance-file" "$prov_file_path" "$prov_file_path_in_container" "ro,Z"
fi

# Mount the Python virtual environment into ${MACARON_WORKSPACE}/python_venv.
if [[ -n "${python_venv_path:-}" ]]; then
    python_venv_in_container="${MACARON_WORKSPACE}/analyze_python_venv_readonly"
    # We copy the mounted directory to `analyze_python_venv_editable` once the container starts running to
    # be able to make changes to the mounted files without affecting the files on host.
    argv_command+=("--python-venv" "${MACARON_WORKSPACE}/analyze_python_venv_editable")

    mount_dir_ro "--python-venv" "$python_venv_path" "$python_venv_in_container"
fi

# MACARON entrypoint - verify-policy command argvs
# This is for macaron verify-policy command.
# Determine the database path to be mounted into ${MACARON_WORKSPACE}/database/macaron.db
if [[ -n "${arg_database:-}" ]]; then
    database_path="${arg_database}"
    file_name="$(basename "${database_path}")"
    database_path_in_container="${MACARON_WORKSPACE}/database/${file_name}"

    argv_command+=("--database" "$database_path_in_container")
    mount_file "-d/--database" "$database_path" "$database_path_in_container" "rw,Z"
fi

# Determine the Datalog policy to be verified by verify-policy command.
if [[ -n "${arg_datalog_policy_file:-}" ]]; then
    datalog_policy_file="${arg_datalog_policy_file}"
    file_name="$(basename "${datalog_policy_file}")"
    datalog_policy_file_in_container="${MACARON_WORKSPACE}/policy/${file_name}"

    argv_command+=("--file" "$datalog_policy_file_in_container")
    mount_file "-f/--file" "$datalog_policy_file" "$datalog_policy_file_in_container" "ro,Z"
fi

# Determine that ~/.gradle/gradle.properties exists to be mounted into ${MACARON_WORKSPACE}/gradle.properties
if [[ -f "$HOME/.gradle/gradle.properties" ]]; then
    mounts+=("-v" "$HOME/.gradle/gradle.properties":"${MACARON_WORKSPACE}/gradle.properties:ro,Z")
fi

# Determine that ~/.m2/settings.xml exists to be mounted into ${MACARON_WORKSPACE}/settings.xml
if [[ -f "$HOME/.m2/settings.xml" ]]; then
    mounts+=("-v" "$HOME/.m2/settings.xml":"${MACARON_WORKSPACE}/settings.xml:ro,Z")
fi

# Set up proxy.
# We respect the host machine's proxy environment variables.
# For Maven and Gradle projects that Macaron needs to analyzes, the proxy configuration
# for Maven wrapper `mvnw` and Gradle wrapper `gradlew` are set using `MAVEN_OPTS` and
# `GRADLE_OPTS` environment variables.
proxy_var_names=(
    "http_proxy"
    "https_proxy"
    "ftp_proxy"
    "no_proxy"
    "HTTP_PROXY"
    "HTTPS_PROXY"
    "FTP_PROXY"
    "NO_PROXY"
    "MAVEN_OPTS"
    "GRADLE_OPTS"
)

for v in "${proxy_var_names[@]}"; do
    proxy_vars+=("-e" "${v}")
done

prod_vars=(
    "-e PYTHONWARNINGS=ignore"  # Turn off Python warnings in the production environment.
)

# Only allocate tty if we detect one. Allocating tty is useful for the user to terminate the container using Ctrl+C.
# However, when not running on a terminal, setting -t will cause errors.
# https://stackoverflow.com/questions/43099116/error-the-input-device-is-not-a-tty
# https://stackoverflow.com/questions/911168/how-can-i-detect-if-my-shell-script-is-running-through-a-pipe
tty=()
if [[ -t 0 ]] && [[ -t 1 ]]; then
    tty+=("-t")
fi

USER_UID="$(id -u)"
USER_GID="$(id -g)"

# Disable unset variable errors from here on to support older bash versions
# where "${array[*]}" and "${array[@]}" expressions throw errors (in set -u mode)
# when the array is empty despite otherwise having the correct behaviour.
set +u

if [[ -z "${entrypoint[*]}" ]];
then
    entrypoint=("macaron")
fi

if [[ -n "${DOCKER_PULL:-}" ]]; then
    if [[ "${DOCKER_PULL}" != @(always|missing|never) ]]; then
        echo "DOCKER_PULL must be one of: always, missing, never (default: always)"
        exit 1
    fi
else
    DOCKER_PULL="always"
fi

echo "Running ${IMAGE}:${MACARON_IMAGE_TAG}"

macaron_args=(
    "${argv_main[@]}"
    "${rest_main[@]}"
    "${command}"
    "${argv_command[@]}"
    "${rest_command[@]}"
)

# For the purpose of testing the arguments passed to macaron, we can set the
# env var `MCN_DEBUG_ARGS=1`.
# In this case, the script will just print the arguments to stderr without
# running the Macaron container.
if [[ -n ${MCN_DEBUG_ARGS:-} ]]; then
    >&2 echo "${macaron_args[@]}"
    exit 0
fi

# By default
# - docker maps the host user $UID to a user with the same $UID in the container.
# - podman maps the host user $UID to the root user in the container.
# To make podman behave similarly to docker, we need to set the following env var.
# Reference: https://docs.podman.io/en/v4.4/markdown/options/userns.container.html.
export PODMAN_USERNS=keep-id

# Pull image based on DOCKER_PULL setting, emulating behaviour of
# docker run --pull ${DOCKER_PULL} ...
# to support older versions of docker that do not support the "--pull" argument.
if [[ "${DOCKER_PULL}" == "always" ]]; then
    docker image pull "${IMAGE}:${MACARON_IMAGE_TAG}"
elif [[ "${DOCKER_PULL}" == "missing" ]]; then
    docker image inspect "${IMAGE}:${MACARON_IMAGE_TAG}" &> /dev/null || docker image pull "${IMAGE}:${MACARON_IMAGE_TAG}"
else
    # "${DOCKER_PULL}" == "never"
    if ! docker image inspect "${IMAGE}:${MACARON_IMAGE_TAG}" &> /dev/null; then
        echo "Docker image '${IMAGE}:${MACARON_IMAGE_TAG}' not found locally and DOCKER_PULL == never, aborting"
        exit 1
    fi
fi

# Make sure commands that need to be cleaned up exist within `set +e` so that when any of them returns a non-zero
# status code, we don't exit right away and still run the token file cleaning up command.
set +e

# Handle tokens.
{
    echo "GITHUB_TOKEN=${GITHUB_TOKEN}"
    echo "MCN_GITLAB_TOKEN=${MCN_GITLAB_TOKEN}"
    echo "MCN_SELF_HOSTED_GITLAB_TOKEN=${MCN_SELF_HOSTED_GITLAB_TOKEN}"
} > ${TOKEN_FILE}
mount_file "macaron_env_file" ${TOKEN_FILE} ${MACARON_WORKSPACE}/${TOKEN_FILE} "rw,Z"

# Force docker to use linux/amd64 platform in order to make docker use emulation on ARM host platforms.
docker run \
    --platform=linux/amd64 \
    --network=host \
    --rm -i "${tty[@]}" \
    -e "USER_UID=${USER_UID}" \
    -e "USER_GID=${USER_GID}" \
    "${proxy_vars[@]}" \
    "${prod_vars[@]}" \
    "${mounts[@]}" \
    "${IMAGE}:${MACARON_IMAGE_TAG}" \
    "${entrypoint[@]}" \
    "${macaron_args[@]}"

clean_up_exit "$?" "$TOKEN_FILE"
