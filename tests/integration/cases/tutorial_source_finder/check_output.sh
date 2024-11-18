#!/bin/bash
# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

[[ "$(jq -r '.commit' output/reports/npm/semver/semver.source.json)" = "eb1380b1ecd74f6572831294d55ef4537dfe1a2a" ]] &&
[[ "$(jq -r '.repo' output/reports/npm/semver/semver.source.json)" = "https://github.com/npm/node-semver" ]]
