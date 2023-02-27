#!/bin/bash

# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

REGISTRY="ghcr.io"
IMAGE_NAME="oracle-samples/macaron"
DIST_PATH="$(pwd)/dist"
REPO_PATH="$(pwd)"

RELEASE_TAG=$1

WHEEL_PATH=$(find "$DIST_PATH" -depth -type f -name 'macaron-*.whl' | head -n 1)
# We need to use the relative path so that it works in the docker context.
WHEEL_PATH=$(realpath --relative-to=$REPO_PATH "$WHEEL_PATH")

if [ -z $RELEASE_TAG ];
then
    docker build -t "$REGISTRY/$IMAGE_NAME:test" --build-arg WHEEL_PATH="$WHEEL_PATH" -f "$REPO_PATH/docker/Dockerfile.final" "$REPO_PATH"
else
    docker build -t "$REGISTRY/$IMAGE_NAME:latest" -t $REGISTRY/$IMAGE_NAME:"$RELEASE_TAG" --build-arg WHEEL_PATH="$WHEEL_PATH" -f "$REPO_PATH/docker/Dockerfile.final" "$REPO_PATH"
    docker push $REGISTRY/$IMAGE_NAME
fi
