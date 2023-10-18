#!/usr/bin/env bash

# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script runs the Macaron Docker image.

if [[ -z ${MACARON_IMAGE_TAG} ]]; then
    MACARON_IMAGE_TAG="latest"
fi

IMAGE="ghcr.io/oracle/macaron"

# Workspace directory inside of the container.
MACARON_WORKSPACE="/home/macaron"

# The entrypoint to run Macaron or the Policy Engine.
# It it set by default to macaron.
# We use an array here to preserve the arguments as provided by the user.
entrypoint=()

# The `macaron` action to execute (e.g. `analyze`, or `verify-policy`)
action=""

# `argv_main` and `argv_action` are arguments whose values changed by this script.
# `argv_main` are arguments of the `macaron` command.
# `argv_action` are arguments of the actions in `macaron` (e.g. `analyze`, or `verify-policy`).
argv_main=()
argv_action=()

# `rest_main` and `rest_action` are arguments whose values are not changed by this script.
# `rest_main` are arguments of the `macaron` command.
# `rest_action` are arguments of the actions in `macaron` (e.g. `analyze`, or `verify-policy`).
rest_main=()
rest_action=()

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
function ensure_absolute_path() {
    if [[ "$1" != /* ]]; then
        echo "$(pwd)/$1"
    else
        echo "$1"
    fi
}

# Ensure a directory exists.
# This method is important since we want to ensure that all docker mounts works
# properly. If we mount a non-existing host directory into the container, docker
# creates an empty directory owned by root, which is not what we really want.
#
# Arguments:
#   $1: The path to the directory.
# Outputs:
#   STDOUT: Error message if the directory does not exist; empty string string otherwise.
function check_dir_exists() {
    if [[ ! -d "$1" ]]; then
        echo "[ERROR] Directory $1 of argument $2 does not exist."
    else
        echo ""
    fi
}

# Ensure a file exists.
#
# Arguments:
#   $1: The path to the file.
# Outputs:
#   STDOUT: Error message if the directory does not exist; empty string string otherwise.
function check_file_exists() {
    if [[ ! -f "$1" ]]; then
        echo "[ERROR] File $1 of argument $2 does not exist."
    else
        echo ""
    fi
}

# Ensure a path exists.
#
# Arguments:
#   $1: The path to a file or directory.
# Outputs:
#   STDOUT: Error message if the file or directory does not exist; empty string string otherwise.
function check_path_exists() {
    if [[ ! -s "$1" ]]; then
        echo "[ERROR] $1 of argument $2 is neither file nor directory."
    else
        echo ""
    fi
}

# Parse main arguments.
while [[ $# -gt 0 ]]; do
    case $1 in
        # Parsing entry points.
        macaron)
            entrypoint+=("macaron")
            ;;
        # Parsing actions for macaron entrypoint.
        analyze|dump-defaults|verify-policy)
            action=$1
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

# Parse action-specific arguments.
if [[ $action == "analyze" ]]; then
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
                rest_action+=("$1")
                ;;
        esac
        shift
    done
elif [[ $action == "verify-policy" ]]; then
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
                rest_action+=("$1")
                ;;
        esac
        shift
    done
fi

# MACARON entrypoint - Main argvs
# Determine the output path to be mounted into ${MACARON_WORKSPACE}/output/
if [[ -n "${arg_output}" ]]; then
    output="${arg_output}"
    err=$(check_dir_exists "${output}" "-o/--output")
    if [[ -n "${err}" ]]; then
        echo "${err}"
        exit 1
    fi
    argv_main+=("--output" "${MACARON_WORKSPACE}/output/")
else
    output=$(pwd)/output
    echo "Setting default output directory to ${output}."
fi

output="$(ensure_absolute_path "${output}")"
# Mounting the necessary .m2 and .gradle directories.
m2_dir="${output}/.m2"
gradle_dir="${output}/.gradle"
mounts+=("-v" "${output}:${MACARON_WORKSPACE}/output:rw,Z")
mounts+=("-v" "${m2_dir}:${MACARON_WORKSPACE}/.m2:rw,Z")
mounts+=("-v" "${gradle_dir}:${MACARON_WORKSPACE}/.gradle:rw,Z")

# Determine the local repos path to be mounted into ${MACARON_WORKSPACE}/output/git_repos/local_repos/
if [[ -n "${arg_local_repos_path}" ]]; then
    local_repos_path="${arg_local_repos_path}"
    err=$(check_dir_exists "${local_repos_path}" "-lr/--local-repos-path")
    if [[ -n "${err}" ]]; then
        echo "${err}"
        exit 1
    fi
    argv_main+=("--local-repos-path" "${MACARON_WORKSPACE}/output/git_repos/local_repos/")

    local_repos_path="$(ensure_absolute_path "${local_repos_path}")"
    mounts+=("-v" "${local_repos_path}:${MACARON_WORKSPACE}/output/git_repos/local_repos/:rw,Z")
fi

# Determine the defaults path to be mounted into ${MACARON_WORKSPACE}/defaults/${file_name}
if [[ -n "${arg_defaults_path}" ]]; then
    defaults_path="${arg_defaults_path}"
    err=$(check_file_exists "${defaults_path}" "-dp/--defaults-path")
    if [[ -n "${err}" ]]; then
        echo "${err}"
        exit 1
    fi
    file_name="$(basename "${defaults_path}")"
    argv_main+=("--defaults-path" "${MACARON_WORKSPACE}/defaults/${file_name}")

    defaults_path="$(ensure_absolute_path "${defaults_path}")"
    mounts+=("-v" "${defaults_path}:${MACARON_WORKSPACE}/defaults/${file_name}:ro")
fi

# Determine the policy path to be mounted into ${MACARON_WORKSPACE}/policy/${file_name}
if [[ -n "${arg_policy}" ]]; then
    policy="${arg_policy}"
    err=$(check_file_exists "${policy}" "-po/--policy")
    if [[ -n "${err}" ]]; then
        echo "${err}"
        exit 1
    fi
    file_name="$(basename "${policy}")"
    argv_main+=("--policy" "${MACARON_WORKSPACE}/policy/${file_name}")

    policy="$(ensure_absolute_path "${policy}")"
    mounts+=("-v" "${policy}:${MACARON_WORKSPACE}/policy/${file_name}:ro")
fi

# MACARON entrypoint - Analyze action argvs
# Determine the template path to be mounted into ${MACARON_WORKSPACE}/template/${file_name}
if [[ -n "${arg_template_path}" ]]; then
    template_path="${arg_template_path}"
    err=$(check_file_exists "${template_path}" "-g/--template-path")
    if [[ -n "${err}" ]]; then
        echo "${err}"
        exit 1
    fi
    file_name="$(basename "${template_path}")"
    argv_action+=("--template-path" "${MACARON_WORKSPACE}/template/${file_name}")

    template_path="$(ensure_absolute_path "${template_path}")"
    mounts+=("-v" "${template_path}:${MACARON_WORKSPACE}/template/${file_name}:ro")
fi

# Determine the config path to be mounted into ${MACARON_WORKSPACE}/config/${file_name}
if [[ -n "${arg_config_path}" ]]; then
    config_path="${arg_config_path}"
    err=$(check_file_exists "${config_path}" "-c/--config-path")
    if [[ -n "${err}" ]]; then
        echo "${err}"
        exit 1
    fi
    file_name="$(basename "${config_path}")"
    argv_action+=("--config-path" "${MACARON_WORKSPACE}/config/${file_name}")

    config_path="$(ensure_absolute_path "${config_path}")"
    mounts+=("-v" "${config_path}:${MACARON_WORKSPACE}/config/${file_name}:ro")
fi

# Determine the sbom path to be mounted into ${MACARON_WORKSPACE}/sbom/${file_name}
if [[ -n "${arg_sbom_path}" ]]; then
    sbom_path="${arg_sbom_path}"
    err=$(check_file_exists "${sbom_path}" "-sbom/--sbom-path")
    if [[ -n "${err}" ]]; then
        echo "${err}"
        exit 1
    fi
    file_name="$(basename "${sbom_path}")"
    argv_action+=("--sbom-path" "${MACARON_WORKSPACE}/sbom/${file_name}")

    sbom_path="$(ensure_absolute_path "${sbom_path}")"
    mounts+=("-v" "${sbom_path}:${MACARON_WORKSPACE}/sbom/${file_name}:ro")
fi

# Determine the provenance expectation path to be mounted into ${MACARON_WORKSPACE}/prov_expectations/${file_name}
if [[ -n "${arg_prov_exp}" ]]; then
    prov_exp="${arg_prov_exp}"
    err=$(check_path_exists "${prov_exp}" "-pe/--provenance-expectation")
    if [[ -n "${err}" ]]; then
        echo "${err}"
        exit 1
    fi
    pe_name="$(basename "${prov_exp}")"
    argv_action+=("--provenance-expectation" "${MACARON_WORKSPACE}/prov_expectations/${pe_name}")

    prov_exp="$(ensure_absolute_path "${prov_exp}")"
    mounts+=("-v" "${prov_exp}:${MACARON_WORKSPACE}/prov_expectations/${pe_name}:ro")
fi

# MACARON entrypoint - verify-policy action argvs
# This is for macaron verify-policy action.
# Determine the database path to be mounted into ${MACARON_WORKSPACE}/database/macaron.db
if [[ -n "${arg_database}" ]]; then
    database="${arg_database}"
    err=$(check_file_exists "${database}" "-d/--database")
    if [[ -n "${err}" ]]; then
        echo "${err}"
        exit 1
    fi
    file_name="$(basename "${database}")"
    argv_action+=("--database" "${MACARON_WORKSPACE}/database/${file_name}")

    database="$(ensure_absolute_path "${database}")"
    mounts+=("-v" "${database}:${MACARON_WORKSPACE}/database/${file_name}:rw,Z")
fi

# Determine the Datalog policy to be verified by verify-policy action.
if [[ -n "${arg_datalog_policy_file}" ]]; then
    datalog_policy_file="${arg_datalog_policy_file}"
    err=$(check_file_exists "${datalog_policy_file}" "-f/--file")
    if [[ -n "${err}" ]]; then
        echo "${err}"
        exit 1
    fi
    file_name="$(basename "${datalog_policy_file}")"
    argv_action+=("--file" "${MACARON_WORKSPACE}/policy/${file_name}")

    datalog_policy_file="$(ensure_absolute_path "${datalog_policy_file}")"
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
    [[ -n ${!v} ]] && proxy_vars+=("-e" "${v}=${!v}")
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

if [[ -n "${DOCKER_PULL}" ]]; then
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
    "${action}"
    "${argv_action[@]}"
    "${rest_action[@]}"
)

# For the purpose of testing the arguments passed to macaron, we can set the
# env var `MCN_DEBUG_ARGS=1`.
# In this case, the script will just print the arguments to stderr without
# running the Macaron container.
if [[ -n ${MCN_DEBUG_ARGS} ]]; then
    >&2 echo "${macaron_args[@]}"
    exit 0
fi

docker run \
    --pull ${DOCKER_PULL} \
    --network=host \
    --rm -i "${tty[@]}" \
    -e "USER_UID=${USER_UID}" \
    -e "USER_GID=${USER_GID}" \
    -e "GITHUB_TOKEN=${GITHUB_TOKEN}" \
    -e "MCN_GITLAB_TOKEN=${MCN_GITLAB_TOKEN}" \
    -e "MCN_SELF_HOSTED_GITLAB_TOKEN=${MCN_SELF_HOSTED_GITLAB_TOKEN}" \
    "${proxy_vars[@]}" \
    "${prod_vars[@]}" \
    "${mounts[@]}" \
    "${IMAGE}:${MACARON_IMAGE_TAG}" \
    "${entrypoint[@]}" \
    "${macaron_args[@]}"
