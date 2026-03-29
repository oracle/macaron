# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Detect security issues and injection risks in GitHub Actions workflows."""

import re
from typing import TypedDict, cast

from macaron.code_analyzer.dataflow_analysis import bash, core, facts
from macaron.code_analyzer.dataflow_analysis.core import NodeForest, traverse_bfs
from macaron.code_analyzer.dataflow_analysis.github import (
    GitHubActionsActionStepNode,
    GitHubActionsNormalJobNode,
    GitHubActionsRunStepNode,
    GitHubActionsWorkflowNode,
)
from macaron.parsers.bashparser_model import CallExpr, is_call_expr, is_lit, is_param_exp
from macaron.parsers.github_workflow_model import Workflow

REMOTE_SCRIPT_RE = re.compile(r"(curl|wget)\s+.*\|\s*(bash|sh|tar)", re.IGNORECASE)

UNTRUSTED_PR_REFS = {
    "${{ github.event.pull_request.head.ref }}",
    "${{ github.head_ref }}",
    "${{ github.event.pull_request.head.sha }}",
    "${{ github.event.pull_request.head.repo.full_name }}",
}

DANGEROUS_TRIGGERS = {
    "pull_request_target",  # elevated token context
    "workflow_run",  # can chain privileged workflows
    "repository_dispatch",  # external event injection risk if misused
    "issue_comment",  # often used to trigger runs; needs strict gating
}


PRIORITY_CRITICAL = 100
PRIORITY_HIGH = 80
PRIORITY_MEDIUM = 60
PRIORITY_LOW = 40
PRIORITY_MIN = 20


class PrioritizedIssue(TypedDict):
    """A workflow security finding with priority metadata."""

    issue: str
    priority: int


class WorkflowFinding(TypedDict):
    """Workflow-level security findings."""

    workflow_name: str
    issues: list[PrioritizedIssue]


def detect_github_actions_security_issues(nodes: NodeForest) -> list[WorkflowFinding]:
    """Detect security issues across GitHub Actions workflow nodes.

    Parameters
    ----------
    nodes : NodeForest
        Parsed workflow node forest used for traversing GitHub Actions workflow callgraphs.

    Returns
    -------
    list[WorkflowFinding]
        A list of workflow-level findings. Each item contains:
        - ``workflow_name``: workflow file path.
        - ``issues``: list of detected security issue messages with priorities.
    """
    findings = []
    for root in nodes.root_nodes:
        for callee in traverse_bfs(root):
            if isinstance(callee, GitHubActionsWorkflowNode):
                if result := analyze_workflow(callee):
                    findings.append(result)
    return findings


def analyze_workflow(
    workflow_node: GitHubActionsWorkflowNode,
) -> WorkflowFinding | None:
    """Analyze a GitHub Actions workflow for security issues.

    Parameters
    ----------
    workflow_node : GitHubActionsWorkflowNode
        The workflow node to analyze.

    Returns
    -------
    dict[str, object] | None
        A finding dictionary with:
        - ``workflow_name``: source filepath of the workflow.
        - ``issues``: list of issue messages.
        Returns ``None`` when no issues are detected.

    Notes
    -----
    The analysis covers trigger hardening, permissions configuration, action pinning,
    checkout risks, remote-script execution heuristics, self-hosted runner usage, and
    dataflow-based expression injection patterns.
    """
    findings: list[PrioritizedIssue] = []
    on_keys = _extract_on_keys(workflow_node.definition)
    seen_jobs: set[str] = set()

    for node in core.traverse_bfs(workflow_node):
        if isinstance(node, GitHubActionsWorkflowNode):
            _append_workflow_level_findings(findings, on_keys, node.definition)
            continue

        if isinstance(node, GitHubActionsNormalJobNode):
            if node.job_id in seen_jobs:
                continue
            seen_jobs.add(node.job_id)
            _append_job_level_findings(findings, node)
            continue

        if isinstance(node, GitHubActionsActionStepNode):
            _append_action_step_findings(findings, node, on_keys)
            continue

        if isinstance(node, GitHubActionsRunStepNode):
            _append_run_step_findings(findings, node)
            continue

        if isinstance(node, bash.BashSingleCommandNode):
            _append_injection_findings(findings, node)

    if "pull_request_target" in on_keys and _has_privileged_trigger_risk_combo(findings):
        _add_finding(
            findings,
            (
                "privileged-trigger: Workflow uses `pull_request_target` with additional risky patterns; "
                "treat this workflow as high risk and harden immediately."
            ),
            PRIORITY_HIGH,
        )

    if findings:
        findings_sorted = sorted(findings, key=lambda finding: (-finding["priority"], finding["issue"]))
        return {"workflow_name": workflow_node.context.ref.source_filepath, "issues": findings_sorted}

    return None


def _extract_on_keys(workflow: Workflow) -> set[str]:
    """Extract the set of event names from a workflow ``on`` section."""
    on_section = workflow.get("on")
    if isinstance(on_section, dict):
        return set(on_section.keys())
    if isinstance(on_section, list):
        return set(on_section)
    return {on_section}


def _append_workflow_level_findings(findings: list[PrioritizedIssue], on_keys: set[str], workflow: Workflow) -> None:
    """Append workflow-level hardening findings."""
    sensitive = sorted(on_keys.intersection(DANGEROUS_TRIGGERS))
    if sensitive:
        _add_finding(
            findings,
            f"sensitive-trigger: Workflow uses {sensitive}. Ensure strict gating (e.g., actor allowlist, "
            "branch protection, and minimal permissions).",
            PRIORITY_LOW,
        )

    if "permissions" not in workflow:
        _add_finding(
            findings,
            "missing-permissions: No explicit workflow permissions defined; defaults may be overly broad.",
            PRIORITY_MEDIUM,
        )
        return

    permissions = workflow.get("permissions")
    if isinstance(permissions, str) and permissions.lower() == "write-all":
        _add_finding(findings, "overbroad-permissions: Workflow uses `permissions: write-all`.", PRIORITY_HIGH)
    if isinstance(permissions, dict) and "pull_request_target" in on_keys:
        for scope, level in permissions.items():
            if isinstance(level, str) and "write" in level.lower():
                _add_finding(
                    findings,
                    f"overbroad-permissions: PR-triggered workflow requests `{scope}: {level}`.",
                    PRIORITY_HIGH,
                )


def _append_job_level_findings(findings: list[PrioritizedIssue], job_node: GitHubActionsNormalJobNode) -> None:
    """Append findings derived from a single job node."""
    runs_on = job_node.definition.get("runs-on")
    if runs_on and "self-hosted" in str(runs_on):
        _add_finding(
            findings,
            f"self-hosted-runner: Job `{job_node.job_id}` runs on self-hosted runners; "
            "ensure isolation and never run untrusted PR code there.",
            PRIORITY_MEDIUM,
        )


def _append_action_step_findings(
    findings: list[PrioritizedIssue],
    action_node: GitHubActionsActionStepNode,
    on_keys: set[str],
) -> None:
    """Append findings derived from an action step node."""
    uses_name = action_node.uses_name
    uses_version = action_node.uses_version
    if (
        uses_name
        and not uses_name.startswith("./")
        and uses_version
        and not re.fullmatch(r"[0-9a-f]{40}", uses_version)
    ):
        _add_finding(findings, f"{uses_name}@{uses_version}", PRIORITY_MIN)

    if uses_name == "actions/checkout":
        ref = _literal_value(action_node.with_parameters.get("ref"))
        if ref in UNTRUSTED_PR_REFS and "pull_request" in on_keys:
            _add_finding(
                findings,
                f"untrusted-fork-code: A checkout step uses untrusted fork code (`ref: {ref}`) on PR event.",
                PRIORITY_CRITICAL,
            )

        persist = _literal_value(action_node.with_parameters.get("persist-credentials"))
        if persist.lower() == "true":
            _add_finding(
                findings,
                "persist-credentials: Checkout uses `persist-credentials: true`; "
                "this may expose GITHUB_TOKEN to subsequent git commands.",
                PRIORITY_MEDIUM,
            )

        if "pull_request_target" in on_keys and ref in UNTRUSTED_PR_REFS:
            _add_finding(
                findings,
                f"pr-target-untrusted-checkout: Workflow uses pull_request_target and checks out PR-controlled ref `{ref}`.",
                PRIORITY_CRITICAL,
            )


def _append_run_step_findings(findings: list[PrioritizedIssue], run_step_node: GitHubActionsRunStepNode) -> None:
    """Append findings derived from a run step node."""
    run_script = run_step_node.definition.get("run", "")
    if isinstance(run_script, str) and REMOTE_SCRIPT_RE.search(run_script):
        _add_finding(
            findings,
            "remote-script-exec: A step appears to download and pipe to shell (`curl|bash`).",
            PRIORITY_HIGH,
        )


def _append_injection_findings(
    findings: list[PrioritizedIssue],
    bash_node: bash.BashSingleCommandNode,
) -> None:
    """Append potential injection findings discovered from parsed bash command nodes."""
    if not is_call_expr(bash_node.definition.get("Cmd")):
        return

    call_exp = cast(CallExpr, bash_node.definition["Cmd"])
    for arg in call_exp.get("Args", []):
        expansion = False
        pr_head_ref = False
        for part in arg.get("Parts", []):
            if is_param_exp(part) and part.get("Param", {}).get("Value") == "github":
                expansion = True
            if is_lit(part) and part.get("Value") in {
                ".event.pull_request.head.ref",
                ".head_ref",
                ".event.issue.body",
                ".event.comment.body",
            }:
                pr_head_ref = True
        if expansion and pr_head_ref:
            _add_finding(findings, f"potential-injection: {arg.get('Parts')}", PRIORITY_CRITICAL)


def _has_privileged_trigger_risk_combo(findings: list[PrioritizedIssue]) -> bool:
    """Return whether findings contain risky patterns that amplify pull_request_target risk."""
    risky_prefixes = (
        "overbroad-permissions:",
        "untrusted-fork-code:",
        "persist-credentials:",
        "remote-script-exec:",
        "pr-target-untrusted-checkout:",
        "potential-injection:",
        "self-hosted-runner:",
    )
    return any(any(finding["issue"].startswith(prefix) for prefix in risky_prefixes) for finding in findings)


def _literal_value(value: facts.Value | None) -> str:
    """Return literal string value from a facts expression when available."""
    if isinstance(value, facts.StringLiteral):
        return value.literal
    return ""


def _add_finding(findings: list[PrioritizedIssue], issue: str, priority: int) -> None:
    """Append a finding with priority metadata."""
    findings.append({"issue": issue, "priority": priority})


# def analyze_workflow(workflow_node: GitHubActionsWorkflowNode, nodes: NodeForest) -> list[dict[str, str]]:
#     """
#     Analyze a GitHub Actions workflow for common security misconfigurations.

#     Issues Detected:
#     - Privileged triggers such as pull_request_target
#     - Execution of untrusted code from forked PRs
#     - Inline shell scripts or unvalidated input usage
#     - Missing permissions or authorization checks
#     """
#     wf = workflow_node.definition
#     findings = []

#     for node in core.traverse_bfs(workflow_node):
#         if isinstance(node, bash.BashSingleCommandNode):
#             # The step in GitHub Actions job that triggers the path in the callgraph.
#             step_node = get_containing_github_step(node, nodes.parents)
#             if is_call_expr(node.definition["Cmd"]):
#                 call_exp = cast(CallExpr, node.definition["Cmd"])
#                 for arg in call_exp["Args"]:
#                     expansion = False
#                     pr_head_ref = False
#                     for part in arg["Parts"]:
#                         if is_param_exp(part) and part["Param"]["Value"] == "github":
#                             expansion = True
#                         if is_lit(part) and part["Value"] == ".event.pull_request.head.ref":
#                             pr_head_ref = True
#                     if expansion and pr_head_ref:
#                         findings.append(
#                             f"Potential injection: {arg['Parts']}"
#                         )

#     # --- 1. Privileged trigger check ---
#     if isinstance(wf.get("on"), dict) and "pull_request_target" in wf["on"]:
#         findings.append(
#             "privileged-trigger: Workflow uses `pull_request_target`, which runs with elevated permissions."
#         )

#     # --- 2. Untrusted code execution ---
#     if isinstance(wf.get("on"), dict) and "pull_request" in wf["on"]:
#         for job_name, job in wf["jobs"].items():
#             if is_normal_job(job) and "steps" in job:
#                 for step in job["steps"]:
#                     uses = step.get("uses", "")
#                     if "actions/checkout" in uses:
#                         ref = step.get("with", {}).get("ref", "")
#                         if ref in ["${{ github.event.pull_request.head.ref }}", "${{ github.head_ref }}"]:
#                             findings.append(
#                                 f"untrusted-fork-code Job `{job_name}` checks out untrusted fork code on PR event."
#                             )

#     # --- 3. Inline shell or unvalidated inputs ---
#     # for job_name, job in wf["jobs"].items():
#     #     if is_normal_job(job) and "steps" in job:
#     #         for step in job["steps"]:
#     #             script = get_run_step(step)
#     #             if script and ("${{ github" in script or "${{ inputs" in script):
#     #                 findings.append(
#     #                     f"unvalidated-input-script: Step `{step.get('name', job_name)}` runs inline shell with expressions."
#     #                 )
#     #             elif script and re.search(r"(curl|wget|bash\s+-c)", script):
#     #                 findings.append(
#     #                     f"inline-shell-risk Step `{step.get('name', job_name)}` runs shell commands directly."
#     #                 )

#     # --- 4. Authorization check ---
#     if "permissions" not in wf:
#         findings.append("missing-permissions: No explicit workflow permissions defined; defaults may be overly broad.")

#     if findings:
#         result: dict[str, list[str]] = {"workflow_name": wf.get("name"), "issues": findings}
#         return result

#     return None
