# GitHub Actions Security Detection Rules

This document describes the findings produced by:
- `src/macaron/code_analyzer/gha_security_analysis/detect_injection.py`
- `src/macaron/slsa_analyzer/checks/github_actions_vulnerability_check.py`

These findings are shown in GitHub job summaries by `scripts/actions/write_job_summary.py` under:
- `workflow_security_issue`
- `third_party_action_risk`

## Finding Groups and Priorities

### `workflow_security_issue`

| finding_type | Default priority | What triggers it |
|---|---:|---|
| `potential-injection` | 100 (critical) | A `run:` command uses attacker-controlled GitHub context values (for example PR head ref, issue/comment body) in shell execution. |
| `untrusted-fork-code` | 100 (critical) | `actions/checkout` uses PR-controlled refs on `pull_request`. |
| `pr-target-untrusted-checkout` | 100 (critical) | `pull_request_target` is used and checkout targets PR-controlled refs. |
| `overbroad-permissions` | 80 (high) | Workflow/job uses broad write permissions (for example `permissions: write-all` or PR-target workflow with write scopes). |
| `remote-script-exec` | 80 (high) | Pipe patterns like `curl ... \| bash/sh/tar` or `wget ... \| ...` are detected. |
| `privileged-trigger` | 80 (high) | `pull_request_target` is combined with other risky patterns in the same workflow. |
| `missing-permissions` | 60 (medium) | Workflow and at least one job omit explicit `permissions`. |
| `self-hosted-runner` | 60 (medium) | Job runs on `self-hosted` runners. |

### `third_party_action_risk`

| finding_type | Default priority | What triggers it |
|---|---:|---|
| `known-vulnerability` | 100 (critical) | OSV reports the referenced GitHub Action version as affected by a known vulnerability. |
| `unpinned-third-party-action` | 20 (low) | A third-party action uses a mutable ref (tag/branch/short SHA) instead of a full 40-char commit SHA. |

## Rule Notes

- Internal actions (`uses: ./...`) are excluded from unpinned-action findings.
- `finding_type` is the subtype; `finding_group` is the report section key.
- For workflow issue findings, line anchors are extracted from workflow metadata or inferred from source text.
- `potential-injection` and `remote-script-exec` findings include structured payload data in the raw issue string (job, step, command, line metadata).

## Remediation Intent by Rule

- `potential-injection`: treat GitHub context as untrusted input; avoid direct shell interpolation.
- `remote-script-exec`: avoid downloader-to-executor pipes; pin and verify scripts.
- `missing-permissions` / `overbroad-permissions`: define explicit least-privilege permissions.
- `untrusted-fork-code` / `pr-target-untrusted-checkout` / `privileged-trigger`: avoid executing PR-controlled code in privileged contexts.
- `self-hosted-runner`: isolate runners and avoid untrusted workloads.
- `known-vulnerability`: upgrade to a non-vulnerable action release.
- `unpinned-third-party-action`: pin actions to immutable full commit SHAs.
