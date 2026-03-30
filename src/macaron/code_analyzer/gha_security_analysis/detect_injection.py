# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Detect security issues and injection risks in GitHub Actions workflows."""

import json
import os
import re
from typing import TypedDict, cast

from macaron.code_analyzer.dataflow_analysis import bash, core, facts
from macaron.code_analyzer.dataflow_analysis.analysis import get_containing_github_job, get_containing_github_step
from macaron.code_analyzer.dataflow_analysis.core import NodeForest, traverse_bfs
from macaron.code_analyzer.dataflow_analysis.github import (
    GitHubActionsActionStepNode,
    GitHubActionsNormalJobNode,
    GitHubActionsRunStepNode,
    GitHubActionsWorkflowNode,
)
from macaron.code_analyzer.gha_security_analysis.recommendation import (
    Recommendation,
    parse_unpinned_action_issue,
    recommend_for_unpinned_action,
    recommend_for_workflow_issue,
    resolve_action_ref_to_sha,
    resolve_action_ref_to_tag,
)
from macaron.parsers.bashparser_model import CallExpr, is_call_expr, is_lit, is_param_exp
from macaron.parsers.github_workflow_model import Workflow
from macaron.slsa_analyzer.git_url import is_commit_hash

UNTRUSTED_PR_REFS = {
    "${{ github.event.pull_request.head.ref }}",
    "${{ github.head_ref }}",
    "${{ github.event.pull_request.head.sha }}",
    "${{ github.event.pull_request.head.repo.full_name }}",
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
                if result := analyze_workflow(callee, nodes=nodes):
                    findings.append(result)
    return findings


def analyze_workflow(workflow_node: GitHubActionsWorkflowNode, nodes: NodeForest) -> WorkflowFinding | None:
    """Analyze a GitHub Actions workflow for security issues.

    Parameters
    ----------
    workflow_node : GitHubActionsWorkflowNode
        The workflow node to analyze.
    nodes : NodeForest
        The full node forest used to resolve parent relationships while analyzing findings.

    Returns
    -------
    WorkflowFinding | None
        A finding dictionary with:
        - ``workflow_name``: source filepath of the workflow.
        - ``issues``: list of issue messages with associated priorities.
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
    workflow_permissions_defined = "permissions" in workflow_node.definition
    has_job_without_permissions = False

    for node in core.traverse_bfs(workflow_node):
        if isinstance(node, GitHubActionsWorkflowNode):
            _append_workflow_level_findings(findings, on_keys, node.definition)
            continue

        if isinstance(node, GitHubActionsNormalJobNode):
            if node.job_id in seen_jobs:
                continue
            seen_jobs.add(node.job_id)
            if "permissions" not in node.definition:
                has_job_without_permissions = True
            _append_job_level_findings(findings, node)
            continue

        if isinstance(node, GitHubActionsActionStepNode):
            _append_action_step_findings(findings, node, on_keys)
            continue

        if isinstance(node, GitHubActionsRunStepNode):
            _append_run_step_findings(findings, node, nodes)
            continue

    if not workflow_permissions_defined and has_job_without_permissions:
        _add_finding(
            findings,
            (
                "missing-permissions: No explicit workflow permissions defined, and one or more jobs also omit "
                "permissions; defaults may be overly broad."
            ),
            PRIORITY_MEDIUM,
        )

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
        return {
            "workflow_name": os.path.relpath(workflow_node.context.ref.source_filepath, os.getcwd()),
            "issues": findings_sorted,
        }

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
    if "permissions" not in workflow:
        return

    permissions = workflow["permissions"]
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
    if uses_name and not uses_name.startswith("./") and uses_version and not is_commit_hash(uses_version):
        step_line = _extract_action_step_line(action_node)
        line_marker = f"[step-line={step_line}] " if step_line else ""
        _add_finding(
            findings,
            f"unpinned-third-party-action: {line_marker}{uses_name}@{uses_version}",
            PRIORITY_MIN,
        )

    if uses_name == "actions/checkout":
        ref = _literal_value(action_node.with_parameters.get("ref"))
        if ref in UNTRUSTED_PR_REFS and "pull_request" in on_keys:
            _add_finding(
                findings,
                f"untrusted-fork-code: A checkout step uses untrusted fork code (`ref: {ref}`) on PR event.",
                PRIORITY_CRITICAL,
            )

        if "pull_request_target" in on_keys and ref in UNTRUSTED_PR_REFS:
            _add_finding(
                findings,
                f"pr-target-untrusted-checkout: Workflow uses pull_request_target and checks out PR-controlled ref `{ref}`.",
                PRIORITY_CRITICAL,
            )


def _append_run_step_findings(
    findings: list[PrioritizedIssue], run_step_node: GitHubActionsRunStepNode, nodes: NodeForest
) -> None:
    """Append findings derived from a run step node."""
    # Traversing a run-step subgraph can reach semantically identical command nodes through
    # multiple CFG/AST paths (for example nested/compound command structures). Track emitted
    # injection findings by stable metadata to avoid duplicate reports for the same command line.
    seen_injection_keys: set[tuple[int | None, str, str, str]] = set()
    for node in core.traverse_bfs(run_step_node):
        # Command-level injection checks rely on parsed call argument parts from single-command nodes.
        if isinstance(node, bash.BashSingleCommandNode):
            _append_injection_findings(findings, node, nodes, seen_injection_keys)
            continue

        # Remote script execution risk is structural: downloader output piped into an executor.
        if isinstance(node, bash.BashPipeNode):
            _append_remote_script_exec_findings(findings, node, run_step_node, nodes)


def _append_remote_script_exec_findings(
    findings: list[PrioritizedIssue],
    pipe_node: bash.BashPipeNode,
    run_step_node: GitHubActionsRunStepNode,
    nodes: NodeForest,
) -> None:
    """Append remote-script-exec findings discovered from parsed bash pipe nodes."""
    if not _is_remote_script_exec_pipe(pipe_node):
        return

    # Map the pipe's script-relative line to workflow source line so summary links jump to YAML.
    script_line = pipe_node.definition["Pos"]["Line"]
    workflow_line = _map_script_line_to_workflow_line(run_step_node, script_line)
    if workflow_line is None:
        workflow_line = _extract_run_step_line(run_step_node)
    job_node = get_containing_github_job(pipe_node, nodes.parents)
    issue_payload = {
        "step_line": workflow_line,
        "script_line": script_line,
        "job": job_node.job_id if job_node else "",
        "step": _extract_step_name(run_step_node),
        "command": _extract_command_text(run_step_node, script_line),
    }
    _add_finding(
        findings,
        f"remote-script-exec: {json.dumps(issue_payload)}",
        PRIORITY_HIGH,
    )


def _is_remote_script_exec_pipe(pipe_node: bash.BashPipeNode) -> bool:
    """Return whether a pipe node matches downloader-to-executor behavior."""
    lhs_words = _extract_statement_words(pipe_node.lhs)
    rhs_words = _extract_statement_words(pipe_node.rhs)
    if not lhs_words or not rhs_words:
        return False

    downloader_cmd = lhs_words[0]
    if downloader_cmd not in {"curl", "wget"}:
        return False

    return _is_executor_invocation(rhs_words)


def _extract_statement_words(statement_node: bash.BashStatementNode) -> list[str]:
    """Extract normalized literal command words from a Bash statement when available."""
    cmd = statement_node.definition.get("Cmd")
    if not is_call_expr(cmd):
        return []
    return _extract_call_words(cmd)


def _extract_call_words(call_expr: CallExpr) -> list[str]:
    """Extract literal word values from a call expression."""
    args = call_expr["Args"]
    words: list[str] = []
    for arg in args:
        parts = arg["Parts"]
        word = "".join(part.get("Value", "") for part in parts if is_lit(part)).strip()
        if not word:
            return []
        words.append(word)
    if not words:
        return []

    normalized = [os.path.basename(word).lower() if idx == 0 else word for idx, word in enumerate(words)]
    return normalized


def _is_executor_invocation(words: list[str]) -> bool:
    """Return whether extracted words represent shell/archive execution."""
    if not words:
        return False
    direct_executors = {"bash", "sh", "tar"}
    wrapper_cmds = {"sudo", "env", "command"}

    command = words[0]
    if command in direct_executors:
        return True
    if command in wrapper_cmds and len(words) > 1:
        wrapped = os.path.basename(words[1]).lower()
        return wrapped in direct_executors
    return False


def _append_injection_findings(
    findings: list[PrioritizedIssue],
    bash_node: bash.BashSingleCommandNode,
    nodes: NodeForest,
    seen_injection_keys: set[tuple[int | None, str, str, str]] | None = None,
) -> None:
    """Append potential injection findings discovered from parsed bash command nodes."""
    if not is_call_expr(bash_node.definition.get("Cmd")):
        return

    call_exp = cast(CallExpr, bash_node.definition["Cmd"])
    for arg in call_exp.get("Args", []):
        parts = arg.get("Parts")
        step_node = get_containing_github_step(bash_node, nodes.parents)
        script_line = _extract_script_line_from_parts(parts)
        expanded_refs = _extract_expanded_github_refs(bash_node, step_node, script_line, parts)
        if _arg_has_attacker_controlled_github_ref(parts) or _has_attacker_controlled_expanded_ref(expanded_refs):
            job_node = get_containing_github_job(bash_node, nodes.parents)
            workflow_line = _map_script_line_to_workflow_line(step_node, script_line)
            if workflow_line is None:
                workflow_line = _extract_run_step_line(step_node)
            job_name = job_node.job_id if job_node else ""
            step_name = _extract_step_name(step_node)
            command_text = _extract_command_text(step_node, script_line)
            dedupe_key = (workflow_line, job_name, step_name, command_text)
            if seen_injection_keys is not None:
                # Prevent duplicate findings when the same risky command is visited via
                # different traversal paths in the run-step subgraph.
                if dedupe_key in seen_injection_keys:
                    continue
                seen_injection_keys.add(dedupe_key)
            issue_payload = {
                "step_line": workflow_line,
                "script_line": script_line,
                "job": job_name,
                "step": step_name,
                "command": command_text,
                "expanded_refs": expanded_refs,
                "parts": arg.get("Parts"),
            }
            _add_finding(findings, f"potential-injection: {json.dumps(issue_payload)}", PRIORITY_CRITICAL)


def _arg_has_attacker_controlled_github_ref(parts: object) -> bool:
    """Return whether argument parts contain attacker-controlled GitHub context expansion.

    Parameters
    ----------
    parts : object
        Parsed argument ``Parts`` payload from the Bash call expression.

    Returns
    -------
    bool
        ``True`` when an attacker-controlled GitHub context reference is detected.
    """
    if not isinstance(parts, list):
        return False

    expansion = False
    pr_head_ref = False
    for part in parts:
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
        return True
    return False


def _has_attacker_controlled_expanded_ref(refs: list[str]) -> bool:
    """Return whether extracted refs include attacker-controlled GitHub context values.

    Parameters
    ----------
    refs : list[str]
        Extracted GitHub expression references.

    Returns
    -------
    bool
        ``True`` if a known attacker-controlled ref is present.
    """
    attacker_controlled = {
        "github.event.pull_request.head.ref",
        "github.head_ref",
        "github.event.issue.body",
        "github.event.comment.body",
    }
    return any(ref in attacker_controlled for ref in refs)


def _extract_expanded_github_refs(
    bash_node: bash.BashSingleCommandNode,
    step_node: GitHubActionsRunStepNode | None,
    script_line: int | None,
    parts: object,
) -> list[str]:
    """Extract normalized expanded GitHub refs from mapping with a line-text fallback.

    Parameters
    ----------
    bash_node : bash.BashSingleCommandNode
        The Bash command node used to resolve parser placeholder mappings.
    step_node : GitHubActionsRunStepNode | None
        The containing run step node, used for fallback extraction from raw run script text.
    script_line : int | None
        1-based line number within the inlined run script for line-targeted fallback extraction.
    parts : object
        Parsed argument ``Parts`` payload from the Bash call expression.

    Returns
    -------
    list[str]
        Ordered list of normalized GitHub expression references.
    """
    refs: list[str] = []
    placeholder_map = dict(bash_node.context.ref.gha_expr_map_items)
    if isinstance(parts, list):
        for part in parts:
            if not is_param_exp(part):
                continue
            placeholder = part.get("Param", {}).get("Value")
            if isinstance(placeholder, str):
                mapped = placeholder_map.get(placeholder)
                if mapped:
                    refs.extend(_extract_github_refs_from_expression(mapped))
    if refs:
        return _deduplicate_preserve_order(refs)

    if step_node is None:
        return []
    # Fallback: some complex shell constructs (for example command substitution in compound
    # test/boolean commands) may not expose mapped placeholders on the current arg parts.
    # In those cases, recover refs directly from the original run-script line text.
    run_script = step_node.definition["run"]
    script_lines = run_script.splitlines()
    if script_line is not None and 1 <= script_line <= len(script_lines):
        line_text = script_lines[script_line - 1]
    else:
        line_text = run_script

    matches = re.findall(r"\$\{\{\s*(.*?)\s*\}\}", line_text)
    fallback_refs: list[str] = []
    for expr in matches:
        fallback_refs.extend(_extract_github_refs_from_expression(expr))
    return _deduplicate_preserve_order(fallback_refs)


def _extract_github_refs_from_expression(expression: str) -> list[str]:
    """Extract github-context reference paths from a GitHub Actions expression body.

    Parameters
    ----------
    expression : str
        Expression text inside ``${{ ... }}``.

    Returns
    -------
    list[str]
        Matched GitHub reference paths (for example ``github.head_ref``).
    """
    return re.findall(r"github(?:\.[A-Za-z0-9_-]+)+", expression)


def _deduplicate_preserve_order(values: list[str]) -> list[str]:
    """Deduplicate string values while preserving insertion order.

    Parameters
    ----------
    values : list[str]
        Input values that may contain duplicates.

    Returns
    -------
    list[str]
        Values in original order with duplicates removed.
    """
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _extract_step_name(step_node: GitHubActionsRunStepNode | None) -> str:
    """Extract a display name for a workflow run step."""
    if step_node is None:
        return ""
    step_name = step_node.definition.get("name")
    if isinstance(step_name, str):
        return step_name
    step_id = step_node.definition.get("id")
    if isinstance(step_id, str):
        return step_id
    return ""


def _extract_command_text(step_node: GitHubActionsRunStepNode | None, script_line: int | None) -> str:
    """Extract a compact command snippet from the run script for display in diagnostics."""
    if step_node is None:
        return ""

    run_script = step_node.definition["run"]
    script_lines = run_script.splitlines()
    if script_line and 1 <= script_line <= len(script_lines):
        return script_lines[script_line - 1].strip()

    for line in script_lines:
        if line.strip():
            return line.strip()
    return ""


def _extract_run_step_line(step_node: GitHubActionsRunStepNode | None) -> int | None:
    """Extract a 1-based workflow line number for a run step when metadata is available."""
    if step_node is None:
        return None

    definition = step_node.definition
    line_container = getattr(definition, "lc", None)
    if line_container is None:
        return _infer_run_step_line_from_source(step_node)

    line = getattr(line_container, "line", None)
    if isinstance(line, int) and line >= 0:
        # ruamel stores line numbers as 0-based.
        return line + 1

    return _infer_run_step_line_from_source(step_node)


def _extract_action_step_line(step_node: GitHubActionsActionStepNode | None) -> int | None:
    """Extract a 1-based workflow line number for an action step when metadata is available."""
    if step_node is None:
        return None

    definition = step_node.definition
    line_container = getattr(definition, "lc", None)
    if line_container is None:
        return _infer_action_step_line_from_source(step_node)

    line = getattr(line_container, "line", None)
    if isinstance(line, int) and line >= 0:
        # ruamel stores line numbers as 0-based.
        return line + 1

    return _infer_action_step_line_from_source(step_node)


def _infer_action_step_line_from_source(step_node: GitHubActionsActionStepNode) -> int | None:
    """Infer an action-step line by matching the ``uses`` value in the workflow source."""
    workflow_path = step_node.context.ref.job_context.ref.workflow_context.ref.source_filepath
    if not workflow_path or not os.path.isfile(workflow_path):
        return None

    uses_name = step_node.uses_name
    uses_version = step_node.uses_version
    if not uses_name or not uses_version:
        return None

    target_uses = f"{uses_name}@{uses_version}"
    step_name = step_node.definition.get("name")
    step_id = step_node.definition.get("id")
    step_identifier = step_name if isinstance(step_name, str) else step_id if isinstance(step_id, str) else None

    try:
        with open(workflow_path, encoding="utf-8") as workflow_file:
            workflow_lines = workflow_file.readlines()
    except OSError:
        return None

    uses_key_re = re.compile(r"^\s*(?:-\s*)?uses\s*:\s*(.*)$")
    candidate_lines: list[int] = []
    for index, line in enumerate(workflow_lines):
        match = uses_key_re.match(line)
        if not match:
            continue
        uses_value = match.group(1).strip().strip("\"'")
        if uses_value == target_uses:
            candidate_lines.append(index + 1)

    if not candidate_lines:
        return None
    if len(candidate_lines) == 1 or not step_identifier:
        return candidate_lines[0]

    for candidate_line in candidate_lines:
        for lookback_index in range(max(0, candidate_line - 8 - 1), candidate_line - 1):
            lookback_line = workflow_lines[lookback_index].strip()
            if lookback_line in {f"name: {step_identifier}", f"id: {step_identifier}"}:
                return candidate_line

    return candidate_lines[0]


def _extract_script_line_from_parts(parts: object) -> int | None:
    """Extract the 1-based script line number from parsed shell argument parts."""
    if not isinstance(parts, list):
        return None

    for part in parts:
        if not isinstance(part, dict):
            continue
        pos = part.get("Pos")
        if not isinstance(pos, dict):
            continue
        line = pos.get("Line")
        if isinstance(line, int) and line > 0:
            return line

    return None


def _map_script_line_to_workflow_line(
    step_node: GitHubActionsRunStepNode | None, script_line: int | None
) -> int | None:
    """Map a line number inside a run script to the corresponding workflow source line."""
    if step_node is None or script_line is None or script_line < 1:
        return None

    workflow_path = step_node.context.ref.job_context.ref.workflow_context.ref.source_filepath
    run_script = step_node.definition.get("run")
    if not workflow_path or not isinstance(run_script, str) or not os.path.isfile(workflow_path):
        return None

    try:
        with open(workflow_path, encoding="utf-8") as workflow_file:
            workflow_lines = workflow_file.readlines()
    except OSError:
        return None

    for block_start, block_lines in _iter_run_blocks(workflow_lines):
        if _normalize_multiline_text("\n".join(block_lines)) != _normalize_multiline_text(run_script):
            continue
        if script_line > len(block_lines):
            return None
        return block_start + script_line - 1

    return None


def _iter_run_blocks(workflow_lines: list[str]) -> list[tuple[int, list[str]]]:
    """Collect run-step script blocks as (1-based start line, content lines)."""
    run_key_re = re.compile(r"^(\s*)(?:-\s*)?run\s*:\s*(.*)$")
    blocks: list[tuple[int, list[str]]] = []
    i = 0
    while i < len(workflow_lines):
        line = workflow_lines[i]
        match = run_key_re.match(line)
        if not match:
            i += 1
            continue

        indent = len(match.group(1))
        run_value = match.group(2).rstrip("\n")

        if run_value.strip().startswith(("|", ">")):
            block_start = i + 2
            block_buffer: list[str] = []
            j = i + 1
            min_indent: int | None = None
            while j < len(workflow_lines):
                candidate = workflow_lines[j]
                if candidate.strip():
                    candidate_indent = len(candidate) - len(candidate.lstrip(" "))
                    if candidate_indent <= indent:
                        break
                    if min_indent is None or candidate_indent < min_indent:
                        min_indent = candidate_indent
                block_buffer.append(candidate.rstrip("\n"))
                j += 1

            if min_indent is None:
                blocks.append((block_start, []))
            else:
                dedented = [b[min_indent:] if len(b) >= min_indent else b for b in block_buffer]
                blocks.append((block_start, dedented))
            i = j
            continue

        inline_value = run_value.strip().strip("\"'")
        blocks.append((i + 1, [inline_value]))
        i += 1

    return blocks


def _normalize_multiline_text(text: str) -> str:
    """Normalize text for robust matching between YAML-extracted and parsed run scripts."""
    return "\n".join(line.rstrip() for line in text.strip("\n").splitlines())


def _infer_run_step_line_from_source(step_node: GitHubActionsRunStepNode) -> int | None:
    """Infer a run step line by matching its script against the workflow source file."""
    workflow_path = step_node.context.ref.job_context.ref.workflow_context.ref.source_filepath
    if not workflow_path or not os.path.isfile(workflow_path):
        return None

    run_script = step_node.definition["run"]
    first_script_line = ""
    for line in run_script.splitlines():
        stripped = line.strip()
        if stripped:
            first_script_line = stripped
            break
    if not first_script_line:
        return None

    try:
        with open(workflow_path, encoding="utf-8") as workflow_file:
            workflow_lines = workflow_file.readlines()
    except OSError:
        return None

    run_key_re = re.compile(r"^\s*(?:-\s*)?run\s*:\s*(.*)$")
    for index, line in enumerate(workflow_lines):
        match = run_key_re.match(line)
        if not match:
            continue

        run_value = match.group(1).strip()
        if run_value and not run_value.startswith("|") and not run_value.startswith(">"):
            inline_value = run_value.strip("\"'")
            if first_script_line in inline_value or inline_value in first_script_line:
                return index + 1
            continue

        run_indent = len(line) - len(line.lstrip(" "))
        for nested_line in workflow_lines[index + 1 :]:
            if not nested_line.strip():
                continue
            nested_indent = len(nested_line) - len(nested_line.lstrip(" "))
            if nested_indent <= run_indent:
                break
            if first_script_line in nested_line.strip():
                return index + 1

    return None


def _has_privileged_trigger_risk_combo(findings: list[PrioritizedIssue]) -> bool:
    """Return whether findings contain risky patterns that amplify pull_request_target risk."""
    risky_prefixes = (
        "overbroad-permissions:",
        "untrusted-fork-code:",
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
    """Append a finding once and keep the highest priority for duplicate issues.

    Parameters
    ----------
    findings : list[PrioritizedIssue]
        Mutable finding list for the current workflow.
    issue : str
        Normalized finding identifier/message.
    priority : int
        Finding priority score.
    """
    for existing in findings:
        if existing["issue"] == issue:
            existing["priority"] = max(existing["priority"], priority)
            return
    findings.append({"issue": issue, "priority": priority})


def get_workflow_issue_type(issue: str) -> str:
    """Extract a normalized workflow issue subtype from issue text."""
    prefix, _, _ = issue.partition(":")
    normalized = prefix.strip().replace("_", "-")
    return normalized or "workflow-security-issue"


def get_workflow_issue_summary(finding_type: str) -> str:
    """Return a concise summary for a workflow issue subtype."""
    finding_summaries = {
        "privileged-trigger": "Privileged trigger can expose elevated token scope to untrusted input.",
        "missing-permissions": "Workflow omits explicit permissions and may inherit broad defaults.",
        "overbroad-permissions": "Workflow requests permissions broader than required.",
        "untrusted-fork-code": "Workflow can execute code controlled by an untrusted fork.",
        "remote-script-exec": "Workflow downloads and executes remote scripts inline.",
        "pr-target-untrusted-checkout": "pull_request_target is combined with checkout of PR-controlled refs.",
        "potential-injection": "Unsafe expansion of attacker-controllable GitHub context can enable command injection.",
        "self-hosted-runner": "Job uses self-hosted runners, increasing blast radius for untrusted code.",
        "workflow-security-issue": "Workflow includes a security issue that requires hardening.",
    }
    return finding_summaries.get(finding_type, "Workflow security finding detected.")


def build_workflow_issue_recommendation(issue: str) -> tuple[str, Recommendation, str]:
    """Build normalized workflow issue recommendation metadata."""
    finding_type = get_workflow_issue_type(issue)
    summary = get_workflow_issue_summary(finding_type)
    recommendation = recommend_for_workflow_issue(issue)
    details = _format_issue_details(finding_type, issue)
    finding_message = f"Summary: {summary} Details: {details} Recommendation: {recommendation.message}"
    return finding_type, recommendation, finding_message


def _format_issue_details(finding_type: str, issue: str) -> str:
    """Format human-readable issue details for job summaries."""
    if finding_type not in {"potential-injection", "remote-script-exec"}:
        return issue

    payload = _parse_issue_payload(issue)
    if not isinstance(payload, dict):
        return issue

    job_name = str(payload.get("job") or "unknown")
    step_name = str(payload.get("step") or "unknown")
    command_text = str(payload.get("command") or "unknown")
    command_text = command_text.replace("`", "'")
    refs = payload.get("expanded_refs")
    refs_display = ""
    if isinstance(refs, list):
        refs_clean = [str(ref) for ref in refs if str(ref)]
        if refs_clean:
            refs_display = f" Expanded refs: `{', '.join(refs_clean)}`"
    return f"Job: {job_name} Step: {step_name} Command: `{command_text}`{refs_display}"


def _parse_issue_payload(issue: str) -> object | None:
    """Parse the serialized issue payload after the finding type prefix."""
    _, _, payload = issue.partition(":")
    payload = payload.strip()
    if not payload:
        return None

    try:
        return cast(object, json.loads(payload))
    except json.JSONDecodeError:
        return None


def build_unpinned_action_recommendation(issue: str, api_client: object) -> tuple[str, str, Recommendation] | None:
    """Build normalized recommendation metadata for an unpinned third-party action finding."""
    parsed_issue = parse_unpinned_action_issue(issue)
    if not parsed_issue:
        return None

    action_name, action_ref = parsed_issue
    resolved_sha = resolve_action_ref_to_sha(api_client, action_name, action_ref)
    resolved_tag = resolve_action_ref_to_tag(action_name, resolved_sha, action_ref)
    recommendation = recommend_for_unpinned_action(action_name, resolved_sha, resolved_tag)
    return action_name, action_ref, recommendation


def extract_workflow_issue_line(issue: str) -> int | None:
    """Extract a 1-based workflow source line number from an issue payload.

    Parameters
    ----------
    issue : str
        Serialized workflow issue string produced by the detector.

    Returns
    -------
    int | None
        The 1-based line number when available; otherwise ``None``.
    """
    step_line_match = re.search(r"\[step-line=(\d+)\]", issue)
    if step_line_match:
        step_line = int(step_line_match.group(1))
        if step_line > 0:
            return step_line

    if not issue.startswith("potential-injection:") and not issue.startswith("remote-script-exec:"):
        return None

    _, _, payload = issue.partition(":")
    if not payload.strip():
        return None

    parsed_payload = _parse_issue_payload(issue)
    if isinstance(parsed_payload, dict):
        payload_step_line = parsed_payload.get("step_line")
        if isinstance(payload_step_line, int) and payload_step_line > 0:
            return payload_step_line

    parts: object | None
    if isinstance(parsed_payload, list):
        parts = parsed_payload
    elif isinstance(parsed_payload, dict):
        parts = parsed_payload.get("parts")
    else:
        parts = None

    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            pos = part.get("Pos")
            if not isinstance(pos, dict):
                continue
            line = pos.get("Line")
            if isinstance(line, int) and line > 0:
                return line

    match = re.search(r"""["']Line["']:\s*(\d+)""", payload)
    if not match:
        return None
    line = int(match.group(1))
    return line if line > 0 else None
