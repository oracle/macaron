#!/bin/bash
# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# When we run the analysis, because we are providing a local repo path, Macaron is not supposed to pull the
# latest changes (i.e the second commit of SOURCE_REPO) into TARGET_REPO.
# Therefore, this analysis is expected to fail because the commit HEAD_COMMIT_SHA does not exist in TARGET_REPO.
HEAD_COMMIT_SHA=$(cat target_commit_sha.txt)
macaron -lr ./output/git_repos/local_repos/ analyze -rp target -d "$HEAD_COMMIT_SHA"
