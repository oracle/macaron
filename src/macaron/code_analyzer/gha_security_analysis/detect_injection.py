import json
import pprint
import re
from typing import Dict, List, cast

from macaron.code_analyzer.dataflow_analysis import bash, core, evaluation
from macaron.code_analyzer.dataflow_analysis.analysis import get_containing_github_step
from macaron.code_analyzer.dataflow_analysis.core import NodeForest, traverse_bfs
from macaron.code_analyzer.dataflow_analysis.github import GitHubActionsWorkflowNode
from macaron.parsers.actionparser import get_run_step
from macaron.parsers.bashparser_model import CallExpr, is_call_expr, is_lit, is_param_exp
from macaron.parsers.github_workflow_model import Workflow, is_normal_job, is_run_step

REMOTE_SCRIPT_RE = re.compile(r"(curl|wget)\s+.*\|\s*(bash|sh|tar)", re.IGNORECASE)
SHA_PINNED_USES_RE = re.compile(r".+@([0-9a-f]{40})$")  # commit SHA pinning

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


def detect_github_actions_security_issues(nodes: NodeForest) -> list[dict[str, list[str]]]:
    findings = []
    for root in nodes.root_nodes:
        for callee in traverse_bfs(root):
            if isinstance(callee, GitHubActionsWorkflowNode):
                if result := analyze_workflow(callee, nodes):
                    findings.append(result)
    return findings


def analyze_workflow(
    workflow_node: GitHubActionsWorkflowNode,
    nodes: NodeForest,
) -> dict[str, object] | None:
    """
    Analyze a GitHub Actions workflow for common security misconfigurations.

    Issues Detected (extended):
    - Privileged triggers such as pull_request_target (and other sensitive triggers)
    - Execution of untrusted code from forked PRs
    - Inline shell scripts or unvalidated input usage (heuristics)
    - Missing permissions or overly broad permissions
    - Actions not pinned to SHA
    - Checkout persist-credentials enabled
    - Self-hosted runner usage
    - Remote script execution patterns (curl|bash)
    """

    wf = workflow_node.definition
    findings: list[str] = []

    on_section = wf.get("on")
    on_keys = set()
    if isinstance(on_section, dict):
        on_keys = set(on_section.keys())
    elif isinstance(on_section, list):
        on_keys = set(on_section)
    elif isinstance(on_section, str):
        on_keys = {on_section}

    # --- A. Triggers that often need extra hardening / gating ---
    sensitive = sorted(on_keys.intersection(DANGEROUS_TRIGGERS))
    if sensitive:
        findings.append(
            f"sensitive-trigger: Workflow uses {sensitive}. Ensure strict gating (e.g., actor allowlist, "
            "branch protection, and minimal permissions)."
        )

    # --- B. Privileged trigger check (existing) ---
    if "pull_request_target" in on_keys:
        findings.append(
            "privileged-trigger: Workflow uses `pull_request_target`, which runs with elevated permissions."
        )

    # --- C. Missing workflow permissions (existing) ---
    if "permissions" not in wf:
        findings.append("missing-permissions: No explicit workflow permissions defined; defaults may be overly broad.")
    else:
        # --- C2. Overly broad workflow permissions (new heuristic) ---
        perms = wf.get("permissions")
        if isinstance(perms, str) and perms.lower() == "write-all":
            findings.append("overbroad-permissions: Workflow uses `permissions: write-all`.")
        if isinstance(perms, dict):
            # Example policy: flag any write permissions on PR-triggered workflows
            if "pull_request_target" in on_keys:
                for scope, level in perms.items():
                    if isinstance(level, str) and "write" in level.lower():
                        findings.append(f"overbroad-permissions: PR-triggered workflow requests `{scope}: {level}`.")

    # Walk jobs/steps for step-level checks.
    jobs = wf.get("jobs", {}) if isinstance(wf.get("jobs"), dict) else {}
    for job_name, job in jobs.items():
        if not is_normal_job(job):
            continue

        # --- D. Self-hosted runners (new) ---
        runs_on = job.get("runs-on")
        if runs_on:
            runs_on_str = str(runs_on)
            if "self-hosted" in runs_on_str:
                findings.append(
                    f"self-hosted-runner: Job `{job_name}` runs on self-hosted runners; "
                    "ensure isolation and never run untrusted PR code there."
                )

        steps = job.get("steps", []) if isinstance(job.get("steps"), list) else []

        for step in steps:
            uses = step.get("uses", "") if isinstance(step, dict) else ""
            run = step.get("run", "") if isinstance(step, dict) else ""

            # --- E. Action SHA pinning (new) ---
            if uses:
                # Ignore local actions "./.github/actions/..."
                if not uses.startswith("./") and not SHA_PINNED_USES_RE.match(uses):
                    findings.append(f"unpinned-action: Job `{job_name}` uses `{uses}` not pinned to a commit SHA.")

            # --- F. Checkout untrusted fork refs on PR event (existing, expanded) ---
            if uses and "actions/checkout" in uses:
                with_section = step.get("with", {}) if isinstance(step.get("with"), dict) else {}
                ref = with_section.get("ref", "")
                if ref in UNTRUSTED_PR_REFS and "pull_request" in on_keys:
                    findings.append(
                        f"untrusted-fork-code: Job `{job_name}` checks out untrusted fork code (`ref: {ref}`) on PR event."
                    )

                # --- G. persist-credentials (new) ---
                # Default is true for checkout; many orgs prefer setting false explicitly.
                persist = with_section.get("persist-credentials", None)
                if persist is True or (isinstance(persist, str) and persist.lower() == "true"):
                    findings.append(
                        f"persist-credentials: Job `{job_name}` uses checkout with `persist-credentials: true`; "
                        "may expose GITHUB_TOKEN to subsequent git commands."
                    )

            # --- H. Remote script execution: curl|bash (new heuristic) ---
            if isinstance(run, str) and REMOTE_SCRIPT_RE.search(run):
                findings.append(
                    f"remote-script-exec: Job `{job_name}` step appears to download and pipe to shell (`curl|bash`)."
                )

            # --- I. Extra dangerous combo: pull_request_target + checkout PR head ref (new) ---
            if "pull_request_target" in on_keys and uses and "actions/checkout" in uses:
                with_section = step.get("with", {}) if isinstance(step.get("with"), dict) else {}
                ref = with_section.get("ref", "")
                if ref in UNTRUSTED_PR_REFS:
                    findings.append(
                        f"pr-target-untrusted-checkout: Job `{job_name}` uses pull_request_target and checks out PR-controlled ref `{ref}`."
                    )

    # --- J. Your existing dataflow-based injection heuristic (kept) ---
    for node in core.traverse_bfs(workflow_node):
        if isinstance(node, bash.BashSingleCommandNode):
            step_node = get_containing_github_step(node, nodes.parents)
            if is_call_expr(node.definition.get("Cmd")):
                call_exp = cast(CallExpr, node.definition["Cmd"])
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
                        findings.append(f"potential-injection: {arg.get('Parts')}")

    if findings:
        return {"workflow_name": wf.get("name"), "issues": findings}

    return None


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
