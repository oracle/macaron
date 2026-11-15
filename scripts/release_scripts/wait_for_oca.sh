#!/usr/bin/env bash
# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

set -euo pipefail

# Skip the PR workaround when the organization no longer requires OCA.
encoded_branch=$(jq -rn --arg branch "$TO_HEAD" '$branch | @uri')
rules=$(gh api "repos/$GH_REPO/rules/branches/$encoded_branch")
oca_required=$(jq -r 'any(.[] | select(.type == "required_status_checks")
    | .parameters.required_status_checks[]; .context == "oca/oracle")' <<< "$rules")
if [[ "$oca_required" == "false" ]]; then
    echo "OCA is not required; continuing with the rebase."
    exit 0
fi

source_branch=${FROM_BASE#origin/}
pr_url=$(gh pr list --repo "$GH_REPO" --base "$TO_HEAD" --head "$source_branch" \
    --state open --json url --jq '.[0].url // empty')
if [[ -z "$pr_url" ]]; then
    pr_url=$(gh pr create --repo "$GH_REPO" --base "$TO_HEAD" --head "$source_branch" \
        --title "chore: synchronize $TO_HEAD after release" \
        --body "Trigger OCA verification before the release workflow rebases $TO_HEAD onto $source_branch. No manual merge is needed.")
fi
head_sha=$(gh pr view "$pr_url" --repo "$GH_REPO" --json headRefOid --jq '.headRefOid')
echo "Waiting for OCA: $pr_url"
deadline=$((SECONDS + ${OCA_CHECK_TIMEOUT_SECONDS:-1800}))
while true; do
    response=$(gh api "repos/$GH_REPO/commits/$head_sha/check-runs?check_name=oca%2Foracle&filter=latest&per_page=100")
    state=$(jq -er '
        [.check_runs[] | select(.name == "oca/oracle" and .app.slug == "oracle-contributor-agreement")]
        | max_by(.id)
        | if . == null or .status != "completed" then "pending" else .conclusion end
    ' <<< "$response")
    case "$state" in
        success) exit 0 ;;
        pending) ;;
        *) echo "OCA did not pass. Inspect $pr_url." >&2; exit 1 ;;
    esac
    if (( SECONDS >= deadline )); then
        echo "Timed out waiting for OCA. Inspect $pr_url." >&2
        exit 1
    fi
    sleep "${OCA_CHECK_INTERVAL_SECONDS:-15}"
done
