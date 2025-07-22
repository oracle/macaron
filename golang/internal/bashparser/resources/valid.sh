#!/bin/bash

# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

set -euo pipefail
if [[ "$COMPILE_BUILDER" = true ]]; then
    echo "Building the builder"
    cd "$BUILDER_DIR"/go/
    go mod vendor
    go build -mod=vendor -o "$BUILDER_BINARY"
    cd -
    mv "${BUILDER_DIR}/go/${BUILDER_BINARY}" .
else
    echo "Fetching the builder with ref: $BUILDER_REF"
    .github/workflows/scripts/builder-fetch.sh
    mv "$BUILDER_RELEASE_BINARY" "$BUILDER_BINARY"
fi
    BUILDER_DIGEST=$(sha256sum "$BUILDER_BINARY" | awk '{print $1}')
    echo "::set-output name=go-builder-sha256::$BUILDER_DIGEST"
    echo "hash of $BUILDER_BINARY is $BUILDER_DIGEST"
    mvn verify deploy
    echo "::set-output name=hashes::$(sha256sum artifact1 artifact2 | base64 -w0)"
