# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# This is a valid GitHub Actions expression.
echo "hash=${{ steps.compute-hash.outputs.hash }}" >> "$GITHUB_OUTPUT"

# These may not be valid GitHub Actions expressions but we want to make
# sure we can handle such cases using greedy regex matching.
echo "hash=${{ ${{ FOO }} }}"
echo "hash=${{ ${ FOO } }}"
echo "hash=${{ $FOO  }}"
echo "hash=${{ {FOO}  }}"
echo "hash=${{}}"
