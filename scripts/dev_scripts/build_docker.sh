#!/bin/bash

# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This script is used to build the Docker image. The built image will always be tagged with `latest`.
#   $1 IMAGE_NAME: The image name to tag the final built image.
#   $2 WORKSPACE: The root path of the Macaron repository which contains the dist/ directory to search for
#       the wheel file.
#   $ RELEASE_TAG: The additionally release tag to tag the final built image. If it's empty, the built image
#       will be additionally tagged with `test`.

IMAGE_NAME=$1
WORKSPACE=$2
RELEASE_TAG=$3

DIST_PATH="${WORKSPACE}/dist"
REPO_PATH="${WORKSPACE}"

WHEEL_PATH=$(find "$DIST_PATH" -depth -type f -name 'macaron-*.whl' | head -n 1)
if [[ -z "${WHEEL_PATH}" ]];
then
    echo "Unable to find Macaron wheel file in ${DIST_PATH}."
    exit 1
fi

# We need to use the relative path so that it works in the docker context.
WHEEL_PATH=$(realpath --relative-to="$REPO_PATH" "$WHEEL_PATH")

if [[ -z "${RELEASE_TAG}" ]];
then
    docker build \
        -t "${IMAGE_NAME}:latest" \
        -t "${IMAGE_NAME}:test" \
        --build-arg WHEEL_PATH="${WHEEL_PATH}" \
        -f "${REPO_PATH}/docker/Dockerfile.final" "${REPO_PATH}"
else
    docker build \
        -t "${IMAGE_NAME}:latest" \
        -t "${IMAGE_NAME}:${RELEASE_TAG}" \
        --build-arg WHEEL_PATH="${WHEEL_PATH}" \
        -f "${REPO_PATH}/docker/Dockerfile.final" "$REPO_PATH"
fi

exit 0
