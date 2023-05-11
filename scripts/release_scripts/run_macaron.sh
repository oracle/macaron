#!/usr/bin/env bash

# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script runs the Macaron Docker image.

if [[ -z ${MACARON_IMAGE_TAG} ]]; then
    MACARON_IMAGE_TAG="latest"
fi

IMAGE="ghcr.io/oracle-samples/macaron"

# Workspace directory inside of the container.
MACARON_WORKSPACE="/home/macaron"

# The entrypoint to run Macaron or the Policy Engine.
# It it set by default to macaron.
# We use an array here to preserve the arguments as provided by the user.
entrypoint=()

# The action to run for each entrypoint.
# For example: `macaron analyze` or `macaron dump-defaults`
action=()

# `argv_main` and `argv_action` are the collections of arguments whose values changed by this script
# before being passed to the Docker image.

# These are arguments for macaron entrypoint.
#   -dp/--defaults-path DEFAULTS_PATH: The path to the defaults configuration file.
#   -h/--help:  Show the help message and exit.
#   -lr/--local-repos-path LOCAL_REPOS_PATH: The directory where Macaron looks for already cloned repositories.
#   -t/--personal_access_token PERSONAL_ACCESS_TOKEN: The GitHub personal access token, which is mandatory for running analysis.
#   -v/--verbose: Run Macaron with more debug logs.

argv_main=()

# These are the sub-commands for a specific action.
# macaron
#   analzye:
#       -g/--template-path TEMPLATE_PATH: The path to the Jinja2 html template (please make sure to use .html or .j2 extensions).
#       -c/--config-path CONFIG_PATH: The path to the user configuration.
#       -pe/--provenance-expectation POLICY: The path to provenance expectation file or directory.
#   dump-defaults:
#   verify-policy:
#       -f/--file FILE: Replace policy file.
#       -d/--database DATABASE: Database path.

argv_action=()

# The rest of the arguments whose values are not changed by this script.
rest=()

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


# Parse arguments.
while [[ $# -gt 0 ]]; do
    case $1 in
        # Parsing entry points.
        macaron)
            entrypoint+=("macaron")
            ;;
        # Parsing actions for macaron entrypoint.
        analyze)
            action+=("analyze")
            ;;
        dump-defaults)
            action+=("dump-defaults")
            ;;
        verify-policy)
            action+=("verify-policy")
            ;;
        # Main argv for main in macaron entrypoint.
        -t|--personal_access_token)
            argv_main+=("-t" "$2")
            shift
            ;;
        -v|--verbose)
            argv_main+=("-v")
            ;;
        -h|--help)
            argv_main+=("-h")
            ;;
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
        # Action argv for macaron entrypoint.
        -g|--template-path)
            arg_template_path="$2"
            shift
            ;;
        -c|--config-path)
            arg_config_path="$2"
            shift
            ;;
        -pe|--provenance-expectation)
            arg_prov_exp="$2"
            shift
            ;;
        -sbom|--sbom-path)
            arg_sbom_path="$2"
            shift
            ;;
        # This flag is duplicated for digest and database.
        -d)
            if [[ "${action[0]}" = "verify-policy" ]];
            then
                arg_database="$2"
                shift
            else
                rest+=("$1" "$2")
                shift
            fi
            ;;

        # Main Argv for verify-policy action.
        --database)
            arg_database="$2"
            shift
            ;;
        -f|--file)
            arg_datalog_policy_file="$2"
            shift
            ;;
        *) # Pass the rest to Macaron.
            rest+=("$1")
            ;;
    esac
    shift
done

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
if [[ -n "${output}" ]]; then
    output="$(ensure_absolute_path "${output}")"
    # Mounting the necessary .m2 and .gradle directories.
    m2_dir="${output}/.m2"
    gradle_dir="${output}/.gradle"
    mounts+=("-v" "${output}:${MACARON_WORKSPACE}/output:rw,Z")
    mounts+=("-v" "${m2_dir}:${MACARON_WORKSPACE}/.m2:rw,Z")
    mounts+=("-v" "${gradle_dir}:${MACARON_WORKSPACE}/.gradle:rw,Z")
fi

# Determine the local repos path to be mounted into ${MACARON_WORKSPACE}/output/git_repos/local_repos/
if [[ -n "${arg_local_repos_path}" ]]; then
    local_repos_path="${arg_local_repos_path}"
    err=$(check_dir_exists "${local_repos_path}" "-lr/--local-repos-path")
    if [[ -n "${err}" ]]; then
        echo "${err}"
        exit 1
    fi
    argv_main+=("--local-repos-path" "${MACARON_WORKSPACE}/output/git_repos/local_repos/")
fi
if [[ -n "${local_repos_path}" ]]; then
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
fi
if [[ -n "${defaults_path}" ]]; then
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
fi
if [[ -n "${policy}" ]]; then
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
fi
if [[ -n "${template_path}" ]]; then
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
fi
if [[ -n "${config_path}" ]]; then
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
fi
if [[ -n "${sbom_path}" ]]; then
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
fi
if [[ -n "${prov_exp}" ]]; then
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
fi
if [[ -n "${database}" ]]; then
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
fi
if [[ -n "${datalog_policy_file}" ]]; then
    datalog_policy_file="$(ensure_absolute_path "${datalog_policy_file}")"
    mounts+=("-v" "${datalog_policy_file}:${MACARON_WORKSPACE}/policy/${file_name}:ro")
fi

# Set up proxy.
# We respect the host machine's proxy environment variables.
proxy_var_names=(
    "http_proxy"
    "https_proxy"
    "ftp_proxy"
    "no_proxy"
    "HTTP_PROXY"
    "HTTPS_PROXY"
    "FTP_PROXY"
    "NO_PROXY"
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

echo "Running ${IMAGE}:${MACARON_IMAGE_TAG}"

docker run \
    --network=host \
    --rm -i "${tty[@]}" \
    -e "USER_UID=${USER_UID}" \
    -e "USER_GID=${USER_GID}" \
    "${proxy_vars[@]}" \
    "${prod_vars[@]}" \
    "${mounts[@]}" \
    "${IMAGE}:${MACARON_IMAGE_TAG}" \
    "${entrypoint[@]}" \
    "${argv_main[@]}" \
    "${action[@]}" \
    "${argv_action[@]}" \
    "${rest[@]}"
