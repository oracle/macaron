#!/bin/sh

# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script runs the Macaron Docker image

# Parameter values
REPO_URL=""
CONFIG_PATH=""
DEFAULTS_PATH=""
DEFAULTS_ARG=""
NETWORK_PARAM="--net host"
MOUNT_DIR="$(pwd)/output"
GH_TOKEN=""
BRANCH=""
DIGEST=""
LOCAL_REPOS_DIR=""
TEMPLATE_PATH=""
POLICY_FILE=""
PROVENANCE_FILE=""
REGISTRY="ghcr.io/oracle-samples"
IMAGE_NAME="macaron"
IMAGE_TAG="latest"

showHelp() {
    echo "USAGE: ./run_macaron.sh [-h/--help] [-d|--disable-proxies] [-R/--repo-url REPO_URL] -T/--token TOKEN -C/--config-path CONFIG_PATH [-B/--branch BRANCH_NAME] [-D/--digest DIGEST] [-S|--skip-deps] [-F|--dump-defaults] [-E/--defaults-path DEFAULTS_PATH] [-L/--local-repos-dir LOCAL_REPOS_DIR] [-I/--image-tag IMAGE_TAG] [-J/--policy POLICY_FILE ] [-V/--verify -K/--provenance PROVENANCE]"
    echo "Run Macaron docker image to analyze a repository. Please make sure the GitHub access token is stored in the GH_TOKEN env variable."
    echo "    -h/--help: Show help message. (optional)"
    echo "    -d/--disable-proxies: Disable proxies for Macaron. If not set, Macaron will use the proxy variables from the host machine."
    echo "    -R/--repo-url: The url to the repository."
    echo "    -T/--token: The GitHub API access token."
    echo "    -C/--config-path: The path to the yaml config file. This option cannot be used together with -R."
    echo "    -B/--branch: The name of the branch we want to checkout. If not specified, Macaron will use the default branch (optional)."
    echo "    -D/--digest: The hash (full form) of the commit we want to analyze. If not specified, Macaron will use the latest commit (optional)."
    echo "    -E/--defaults-path: The path to the defaults.ini file. Use dump-defaults to generate a template."
    echo "    -F/--dump-defaults: Set to true to dump the default configuration values in defaults.ini (optional)."
    echo "    -S/--skip-deps: Set to true to skip automatic dependency resolution (optional)."
    echo "    -L/--local-repos-dir: The directory on the host machine that Macaron can look for local repositories. This value must be an absolute path (optional)."
    echo "    -I/--image-tag: The version of the Macaron Docker image (optional)."
    echo "    -G/--template-path: The path to the custom template file (optional)."
    echo "    -J/--policy: The path to the policy file. Used together with -V/--verify option."
    echo "    -V/--verify: Verify the provenance content against a policy file. Note that using this option will override any other options and does not run the analysis. USAGE: --verify <POLICY> <PROVENANCE>."
    echo "    -K/--provenance: The path to the provenance to verify. Used together with -V/--verify option."
    echo "Example running without config: ./run_macaron.sh -R https://github.com/apache/maven.git -T \$GH_TOKEN"
    echo "Example running with config: ./run_macaron.sh -T \$GH_TOKEN -C ./examples/maven_config.yaml"
    echo "Example running with proxies disabled: ./run_macaron.sh -d -T \$GH_TOKEN -C ./examples/maven_config.yaml"
    echo "Example to verify a provenance against a policy: ./scripts/release_scripts/macaron_release/run_macaron.sh -T \$GH_TOKEN -I staging -V --policy ./examples/slsa_verifier_policy.yaml --provenance ./path/to/provenance/file"
}

readLink() {
    # Print resolved symbolic links or canonical file names
    # OSX compatibility solution from https://stackoverflow.com/a/1116890
    # simulate readlink --canonicalize-existing, which is not available in OSX

    TARGET_FILE=$1

    cd `dirname $TARGET_FILE`
    TARGET_FILE=`basename $TARGET_FILE`

    # Iterate down a (possible) chain of symlinks
    while [ -L "$TARGET_FILE" ]
    do
        TARGET_FILE=`readlink $TARGET_FILE`
        cd `dirname $TARGET_FILE`
        TARGET_FILE=`basename $TARGET_FILE`
    done

    # Compute the canonicalized name by finding the physical path
    # for the directory we're in and appending the target file.
    PHYS_DIR=`pwd -P`
    RESULT=$PHYS_DIR/$TARGET_FILE
    echo $RESULT
}

if [ $# -lt 1 ];
then
    showHelp
    exit 1
fi

# Get input arguments
OPTION=`getopt -a -l "help,disable-proxies,skip-deps,dump-defaults,verify,policy:,provenance:,repo-url:,token:,config-path:,defaults-path:,branch:,digest:,local-repos-dir:,image-tag:,template-path:" -o "hdSFVJ:K:R:T:C:B:D:E:L:I:G:" -- "$@"`
eval set -- "$OPTION"

# Set values from input arguments
while true
do
    case $1 in
        -h|--help)
            showHelp
            exit 0
            ;;
        -d|--disable-proxies)
            NETWORK_PARAM=""
            ;;
        -R|--repo-url)
            shift
            REPO_URL=$1
            ;;
        -T|--token)
            shift
            GH_TOKEN=$1
            ;;
        -C|--config-path)
            shift
            CONFIG_PATH=$(readLink $1)
            ;;
        -B|--branch)
            shift
            BRANCH=$1
            ;;
        -D|--digest)
            shift
            DIGEST=$1
            ;;
        -E|--defaults-path)
            shift
            DEFAULTS_PATH=$(readLink $1)
            ;;
        -S|--skip-deps)
            SKIPDEPS="true"
            ;;
        -F|--dump-defaults)
            DUMP="true"
            ;;
        -L|--local-repos-dir)
            shift
            LOCAL_REPOS_DIR=$1
            ;;
        -I|--image-tag)
            shift
            IMAGE_TAG=$1
            ;;
        -G|--template-path)
            shift
            TEMPLATE_PATH=$(readLink $1)
            ;;
        -V|--verify)
            VERIFY="true"
            ;;
        -J|--policy)
            shift
            POLICY_FILE=$(readLink $1)
            ;;
        -K|--provenance)
            shift
            PROVENANCE_FILE=$(readLink $1)
            ;;
        --)
            shift
            break
            ;;
    esac
shift
done

# Start the container and run the SLSA analysis
IMAGE_URL="$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

if [ -n "$REPO_URL" ] && [ -n "$CONFIG_PATH" ];
then
    echo "Cannot provide both repo path and config file. Please choose one."
    showHelp
    exit 1
fi

if [ -z "$DUMP" ]  && [ -z "$VERIFY" ] && { { [ -z "$REPO_URL" ] && [ -z "$CONFIG_PATH" ]; } || [ -z "$GH_TOKEN" ]; };
then
    echo "Missing parameters."
    showHelp
    exit 1
fi

if [ -n "$CONFIG_PATH" ] && [ ! -f "$CONFIG_PATH" ] ;
then
    echo "The configuration file does not exist."
    showHelp
    exit 1
fi

if [ -n "$DEFAULTS_PATH" ] && [ ! -f "$DEFAULTS_PATH" ] ;
then
    echo "The defaults.ini file does not exist."
    showHelp
    exit 1
fi

if [ -n "$TEMPLATE_PATH" ] && [ ! -f "$TEMPLATE_PATH" ] ;
then
    echo "Cannot find the template file."
    showHelp
    exit 1
fi

if [ -n "$POLICY_FILE" ] && [ ! -f "$POLICY_FILE" ] ;
then
    echo "Cannot find the policy file."
    exit 1
fi

# The verify sub command for Macaron.
if [ -n "$VERIFY" ] && { [ -z "$POLICY_FILE" ] || [ -z "$PROVENANCE_FILE" ]; };
then
    echo "USAGE: ./run_macaron.sh --policy <POLICY> --verify --provenance <PROVENANCE>"
    echo "Note: to use the verify command, make sure the policy and the provenance file paths are provided."
    exit 1
fi
if [ -n "$PROVENANCE_FILE" ] && [ ! -f "$PROVENANCE_FILE" ] ;
then
    echo "Cannot find the provenance file."
    exit 1
fi

# Resolve proxy. This will ensure to override any proxy configuration of the
# Docker client.
if [ -z "$NETWORK_PARAM" ];
then
    # No VPN, should not have proxy.
    echo "Because VPN off is selected, we override all proxy environment variables in the container to empty."
    for e in http_proxy https_proxy no_proxy ftp_proxy HTTP_PROXY HTTPS_PROXY NO_PROXY FTP_PROXY; do
        DOCKER_ENV="$DOCKER_ENV -e ${e}"
    done
else
    # If VPN is enabled, get proxy configuration from env variables.
    # Proxy variables do not exist will be set to empty to override configuration
    # from config.json
    has_proxy=false
    for e in http_proxy https_proxy no_proxy ftp_proxy HTTP_PROXY HTTPS_PROXY NO_PROXY FTP_PROXY; do
        exp=$(eval echo \$$e)
        if [ -n "${exp}" ];
        then
            has_proxy=true
		    DOCKER_ENV="$DOCKER_ENV -e ${e}=${exp}"
        else
            # Make this env variable to empty.
            DOCKER_ENV="$DOCKER_ENV -e ${e}"
        fi
    done

    if [ "$has_proxy" = false ];
    then
        echo "No proxy configuration discovered."
        echo "Please set the proxy environment variables OR run this script with -d (Disable proxies)."
        echo "To set proxy environment variables: "
        echo "    $ export {http,https,ftp}_proxy=http://www-proxy-syd.au.oracle.com:80"
        echo "    $ export no_proxy=localhost,127.0.0.1,.oracle.com,.oraclecorp.com"
        exit 1
    fi
fi

if [ ! -d "$MOUNT_DIR" ];
then
    echo "Create output dir for Macaron at $MOUNT_DIR"
    mkdir -p $MOUNT_DIR
fi

if [ -n "$DEFAULTS_PATH" ];
then
    DEFAULTS_ARG="--mount type=bind,source=$DEFAULTS_PATH,target=/home/macaron/defaults.ini"
fi

DOCKER_PARAMS="--rm -i $NETWORK_PARAM -v $MOUNT_DIR/.m2:/home/macaron/.m2 -v $MOUNT_DIR:/home/macaron/workspace"

# Only allocate tty if we detect one. Allocating tty is useful for the user to terminate the container using Ctrl+C.
# However, when not running on a terminal, setting -t will cause errors.
# https://stackoverflow.com/questions/43099116/error-the-input-device-is-not-a-tty
# https://stackoverflow.com/questions/911168/how-can-i-detect-if-my-shell-script-is-running-through-a-pipe
# https://docs.docker.com/engine/reference/commandline/run/#options
if [ -t 0 ] && [ -t 1 ]; then
    DOCKER_PARAMS="$DOCKER_PARAMS -t"
fi

if [ -n "$LOCAL_REPOS_DIR" ];
then
    # We just need to mount the dir (in the host machine) specified by the user to the default local repos dir in Macaron.
    DOCKER_PARAMS="$DOCKER_PARAMS -v $LOCAL_REPOS_DIR:/home/macaron/workspace/git_repos/local_repos"
fi

if [ -n "$CONFIG_PATH" ];
then
    DOCKER_PARAMS="$DOCKER_PARAMS --mount type=bind,source=$CONFIG_PATH,target=/home/macaron/config/macaron_config.json $DEFAULTS_ARG"
else
    DOCKER_PARAMS="$DOCKER_PARAMS $DEFAULTS_ARG"
fi

if [ -n "$TEMPLATE_PATH" ];
then
    TEMPLATE_DIR=$(dirname $TEMPLATE_PATH)
    DOCKER_PARAMS="$DOCKER_PARAMS -v $TEMPLATE_DIR:/home/macaron/workspace/template/"
fi

if [ -n "$POLICY_FILE" ];
then
    DOCKER_PARAMS="$DOCKER_PARAMS --mount type=bind,source=$POLICY_FILE,target=/home/macaron/policy/$(basename $POLICY_FILE)"
fi

if [ -n "$VERIFY" ];
then
    DOCKER_PARAMS="$DOCKER_PARAMS --mount type=bind,source=$PROVENANCE_FILE,target=/home/macaron/policy/$(basename $PROVENANCE_FILE)"
fi

if [ -n "$DUMP" ];
then
    MACARON_PARAMS="dump_defaults"
elif [ -n "$VERIFY" ];
# Using the verify command will not perform any analysis.
then
    MACARON_PARAMS="-t $GH_TOKEN -o /home/macaron/workspace/ -po /home/macaron/policy/$(basename $POLICY_FILE) verify -pr /home/macaron/policy/$(basename $PROVENANCE_FILE)"
else
    MACARON_PARAMS="-t $GH_TOKEN -o /home/macaron/workspace/ analyze"

    if [ -n "$REPO_URL" ];
    then
        analyze_PARAMS="-rp $REPO_URL"
        if [ -n "$BRANCH" ];
        then
            analyze_PARAMS="$analyze_PARAMS -b $BRANCH"
        fi

        if [ -n "$DIGEST" ];
        then
            analyze_PARAMS="$analyze_PARAMS -d $DIGEST"
        fi
    else
        if [ -n "$BRANCH" ] || [ -n "$DIGEST" ];
        then
            echo "Cannot specify branch or commit digest when using config file. Please put them in the config file."
            showHelp
            exit 1
        fi

        analyze_PARAMS="-c /home/macaron/config/macaron_config.json"
    fi

    if [ -n "$SKIPDEPS" ];
    then
        analyze_PARAMS="$analyze_PARAMS --skip-deps"
    fi

    if [ -n "$TEMPLATE_PATH" ];
    then
        analyze_PARAMS="$analyze_PARAMS -g /home/macaron/workspace/template/$(basename $TEMPLATE_PATH)"
    fi
fi

USER_UID=`id -u`
USER_GID=`id -g`
echo "Docker container env: $DOCKER_ENV"
echo "Running Macaron $IMAGE_TAG ..."
exec docker run -e USER_GID=$USER_GID -e USER_UID=$USER_UID $DOCKER_ENV $DOCKER_PARAMS $IMAGE_URL $MACARON_PARAMS $analyze_PARAMS
