#!/bin/bash
# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

WORKSPACE=$(pwd)

SOURCE_REPO="$WORKSPACE/output/git_repos/local_repos/source"
TARGET_REPO="$WORKSPACE/output/git_repos/local_repos/target"

mkdir -p  "$SOURCE_REPO"

# Prepare the first commit for the repository.
cd "$SOURCE_REPO" || exit 1
git init
git config --local user.email "testing@example.com"
git config --local user.name "Testing"
echo 1 >> test1.txt
git add test1.txt
git commit -m "First commit"

# Clone from SOURCE_REPO. TARGET_REPO will be identical to SOURCE_REPO and contain only the first commit.
mkdir -p "$TARGET_REPO"
git clone "$SOURCE_REPO" "$TARGET_REPO"

# Create a second commit in SOURCE_REPO.
# Note that after this commit is created, TARGET_REPO will not have the second commit.
# However, because TARGET_REPO's remote origin points to SOURCE_REPO, the second commit can be pulled from SOURCE_REPO.
cd "$SOURCE_REPO" || exit 1
echo 2 >> test2.txt
git add test2.txt
git commit -m "Second commit"
# This is the SHA for the second commit, which exists in SOURCE_REPO but not in TARGET_REPO yet.
HEAD_COMMIT_SHA=$(git rev-parse HEAD)

# We store the commit sha to a file so that we can read from it within the test.sh script.
cd "$WORKSPACE" || exit 1
echo "$HEAD_COMMIT_SHA" > target_commit_sha.txt
