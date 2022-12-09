#!/bin/sh
# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# helper script to pass proxy environment variables to `docker build` as build arguments
# usage: build.sh -t <image name> <path to Dockerfile>

DOCKER_ENV=""
for e in http_proxy https_proxy no_proxy; do
	# in bash indirect variable expansion would be just: ${!e}
	exp=$(eval echo \$$e)
	if [ -n "${exp}" ]; then
		DOCKER_ENV="$DOCKER_ENV --build-arg ${e}=${exp}"
	fi
done
# trim whitespace
DOCKER_ENV="${DOCKER_ENV#"${DOCKER_ENV%%[![:space:]]*}"}"

set -x
exec docker build $DOCKER_ENV $@
