#!/bin/bash

# Copyright (c) 2023 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script is used to build the Docker image. The built image will always be tagged with `latest`.
#   $1 IMAGE_NAME: The image name to tag the final built image.
#   $2 WORKSPACE: The root path of the Macaron repository which contains the dist/ directory to search for
#       the wheel file.
#   $ RELEASE_TAG: The additionally release tag to tag the final built image. If it's empty, the built image
#       will be additionally tagged with `test`.

if [ "$#" -ne 3 ];
then
    echo "Required arguments are missing" && exit 1
fi
IMAGE_NAME=$1
WORKSPACE=$2
RELEASE_TAG=$3

DIST_PATH="${WORKSPACE}/dist"
REPO_PATH="${WORKSPACE}"

SIMPLE_INDEX_PATH=$(find "${DIST_PATH}" -depth -type f -name 'macaron-*-pep503-simple-index.tar' | head -n 1)
if [[ -z "${SIMPLE_INDEX_PATH}" ]]; then
    echo "Unable to find Macaron Simple Index in ${DIST_PATH}."
    exit 1
fi
SIMPLE_INDEX_PATH=$(realpath --relative-to "${REPO_PATH}" "${SIMPLE_INDEX_PATH}")

REQUIREMENTS_PATH=$(find "${DIST_PATH}" -depth -type f -name 'macaron-*-requirements.txt' | head -n 1)
if [[ -z "${REQUIREMENTS_PATH}" ]]; then
    echo "Unable to find Macaron requirements.txt in ${DIST_PATH}."
    exit 1
fi
REQUIREMENTS_PATH=$(realpath --relative-to "${REPO_PATH}" "${REQUIREMENTS_PATH}")

if [[ -z "${RELEASE_TAG}" ]];
then
    docker build \
        --tag "${IMAGE_NAME}:latest" \
        --tag "${IMAGE_NAME}:test" \
        --build-arg SIMPLE_INDEX_PATH="${SIMPLE_INDEX_PATH}" \
        --build-arg REQUIREMENTS_PATH="${REQUIREMENTS_PATH}" \
        --file "${REPO_PATH}/docker/Dockerfile.final" "${REPO_PATH}"
else
    docker build \
        --tag "${IMAGE_NAME}:latest" \
        --tag "${IMAGE_NAME}:${RELEASE_TAG}" \
        --build-arg SIMPLE_INDEX_PATH="${SIMPLE_INDEX_PATH}" \
        --build-arg REQUIREMENTS_PATH="${REQUIREMENTS_PATH}" \
        --file "${REPO_PATH}/docker/Dockerfile.final" "$REPO_PATH"
fi

exit 0
