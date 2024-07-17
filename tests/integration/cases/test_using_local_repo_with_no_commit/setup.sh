#!/bin/bash
# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

mkdir -p output/git_repos/local_repos/empty_repo
cd output/git_repos/local_repos/empty_repo || exit 1
git init
