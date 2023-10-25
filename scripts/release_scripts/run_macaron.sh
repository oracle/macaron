#!/usr/bin/env bash

# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
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
# This option is not enabled by default for bash on some systems, most notably MacOS
# where the default bash version is very old.
# Reference: https://www.gnu.org/software/bash/manual/html_node/The-Shopt-Builtin.html
shopt -s extglob

if [[ -z ${MACARON_IMAGE_TAG:-} ]]; then
    MACARON_IMAGE_TAG="latest"
fi

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

# Log error (to stderr).
log_err() {
    echo "[ERROR]: $*" >&2
}

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
    if [[ ! -d "$1" ]]; then
        log_err "Directory $1 of argument $2 does not exist."
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
            -c|--config-path)
                arg_config_path="$2"
                shift
                ;;
            -g|--template-path)
                arg_template_path="$2"
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
    assert_dir_exists "${output}" "-o/--output"
    argv_main+=("--output" "${MACARON_WORKSPACE}/output/")
else
    output=$(pwd)/output
    echo "Setting default output directory to ${output}."
fi

output="$(to_absolute_path "${output}")"
# Mounting the necessary .m2 and .gradle directories.
m2_dir="${output}/.m2"
gradle_dir="${output}/.gradle"
mounts+=("-v" "${output}:${MACARON_WORKSPACE}/output:rw,Z")
mounts+=("-v" "${m2_dir}:${MACARON_WORKSPACE}/.m2:rw,Z")
mounts+=("-v" "${gradle_dir}:${MACARON_WORKSPACE}/.gradle:rw,Z")

# Determine the local repos path to be mounted into ${MACARON_WORKSPACE}/output/git_repos/local_repos/
if [[ -n "${arg_local_repos_path:-}" ]]; then
    local_repos_path="${arg_local_repos_path}"
    assert_dir_exists "${local_repos_path}" "-lr/--local-repos-path"
    argv_main+=("--local-repos-path" "${MACARON_WORKSPACE}/output/git_repos/local_repos/")

    local_repos_path="$(to_absolute_path "${local_repos_path}")"
    mounts+=("-v" "${local_repos_path}:${MACARON_WORKSPACE}/output/git_repos/local_repos/:rw,Z")
fi

# Determine the defaults path to be mounted into ${MACARON_WORKSPACE}/defaults/${file_name}
if [[ -n "${arg_defaults_path:-}" ]]; then
    defaults_path="${arg_defaults_path}"
    assert_file_exists "${defaults_path}" "-dp/--defaults-path"
    file_name="$(basename "${defaults_path}")"
    argv_main+=("--defaults-path" "${MACARON_WORKSPACE}/defaults/${file_name}")

    defaults_path="$(to_absolute_path "${defaults_path}")"
    mounts+=("-v" "${defaults_path}:${MACARON_WORKSPACE}/defaults/${file_name}:ro")
fi

# Determine the policy path to be mounted into ${MACARON_WORKSPACE}/policy/${file_name}
if [[ -n "${arg_policy:-}" ]]; then
    policy="${arg_policy}"
    assert_file_exists "${policy}" "-po/--policy"
    file_name="$(basename "${policy}")"
    argv_main+=("--policy" "${MACARON_WORKSPACE}/policy/${file_name}")

    policy="$(to_absolute_path "${policy}")"
    mounts+=("-v" "${policy}:${MACARON_WORKSPACE}/policy/${file_name}:ro")
fi

# MACARON entrypoint - Analyze command argvs
# Determine the template path to be mounted into ${MACARON_WORKSPACE}/template/${file_name}
if [[ -n "${arg_template_path:-}" ]]; then
    template_path="${arg_template_path}"
    assert_file_exists "${template_path}" "-g/--template-path"
    file_name="$(basename "${template_path}")"
    argv_command+=("--template-path" "${MACARON_WORKSPACE}/template/${file_name}")

    template_path="$(to_absolute_path "${template_path}")"
    mounts+=("-v" "${template_path}:${MACARON_WORKSPACE}/template/${file_name}:ro")
fi

# Determine the config path to be mounted into ${MACARON_WORKSPACE}/config/${file_name}
if [[ -n "${arg_config_path:-}" ]]; then
    config_path="${arg_config_path}"
    assert_file_exists "${config_path}" "-c/--config-path"
    file_name="$(basename "${config_path}")"
    argv_command+=("--config-path" "${MACARON_WORKSPACE}/config/${file_name}")

    config_path="$(to_absolute_path "${config_path}")"
    mounts+=("-v" "${config_path}:${MACARON_WORKSPACE}/config/${file_name}:ro")
fi

# Determine the sbom path to be mounted into ${MACARON_WORKSPACE}/sbom/${file_name}
if [[ -n "${arg_sbom_path:-}" ]]; then
    sbom_path="${arg_sbom_path}"
    assert_file_exists "${sbom_path}" "-sbom/--sbom-path"
    file_name="$(basename "${sbom_path}")"
    argv_command+=("--sbom-path" "${MACARON_WORKSPACE}/sbom/${file_name}")

    sbom_path="$(to_absolute_path "${sbom_path}")"
    mounts+=("-v" "${sbom_path}:${MACARON_WORKSPACE}/sbom/${file_name}:ro")
fi

# Determine the provenance expectation path to be mounted into ${MACARON_WORKSPACE}/prov_expectations/${file_name}
if [[ -n "${arg_prov_exp:-}" ]]; then
    prov_exp="${arg_prov_exp}"
    assert_path_exists "${prov_exp}" "-pe/--provenance-expectation"
    pe_name="$(basename "${prov_exp}")"
    argv_command+=("--provenance-expectation" "${MACARON_WORKSPACE}/prov_expectations/${pe_name}")

    prov_exp="$(to_absolute_path "${prov_exp}")"
    mounts+=("-v" "${prov_exp}:${MACARON_WORKSPACE}/prov_expectations/${pe_name}:ro")
fi

# MACARON entrypoint - verify-policy command argvs
# This is for macaron verify-policy command.
# Determine the database path to be mounted into ${MACARON_WORKSPACE}/database/macaron.db
if [[ -n "${arg_database:-}" ]]; then
    database="${arg_database}"
    assert_file_exists "${database}" "-d/--database"
    file_name="$(basename "${database}")"
    argv_command+=("--database" "${MACARON_WORKSPACE}/database/${file_name}")

    database="$(to_absolute_path "${database}")"
    mounts+=("-v" "${database}:${MACARON_WORKSPACE}/database/${file_name}:rw,Z")
fi

# Determine the Datalog policy to be verified by verify-policy command.
if [[ -n "${arg_datalog_policy_file:-}" ]]; then
    datalog_policy_file="${arg_datalog_policy_file}"
    assert_file_exists "${datalog_policy_file}" "-f/--file"
    file_name="$(basename "${datalog_policy_file}")"
    argv_command+=("--file" "${MACARON_WORKSPACE}/policy/${file_name}")

    datalog_policy_file="$(to_absolute_path "${datalog_policy_file}")"
    mounts+=("-v" "${datalog_policy_file}:${MACARON_WORKSPACE}/policy/${file_name}:ro")
fi

# Determine that ~/.gradle/gradle.properties exists to be mounted into ${MACARON_WORKSPACE}/gradle.properties
if [[ -f "$HOME/.gradle/gradle.properties" ]]; then
    mounts+=("-v" "$HOME/.gradle/gradle.properties":"${MACARON_WORKSPACE}/gradle.properties:ro")
fi

# Determine that ~/.m2/settings.xml exists to be mounted into ${MACARON_WORKSPACE}/settings.xml
if [[ -f "$HOME/.m2/settings.xml" ]]; then
    mounts+=("-v" "$HOME/.m2/settings.xml":"${MACARON_WORKSPACE}/settings.xml:ro")
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

docker run \
    --pull ${DOCKER_PULL} \
    --network=host \
    --rm -i "${tty[@]}" \
    -e "USER_UID=${USER_UID}" \
    -e "USER_GID=${USER_GID}" \
    -e GITHUB_TOKEN \
    -e MCN_GITLAB_TOKEN \
    -e MCN_SELF_HOSTED_GITLAB_TOKEN \
    "${proxy_vars[@]}" \
    "${prod_vars[@]}" \
    "${mounts[@]}" \
    "${IMAGE}:${MACARON_IMAGE_TAG}" \
    "${entrypoint[@]}" \
    "${macaron_args[@]}"
