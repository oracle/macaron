# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for GitHub Actions security analysis detection heuristics."""

import os
from pathlib import Path

import pytest

from macaron.code_analyzer.gha_security_analysis.detect_injection import (
    PrioritizedIssue,
    WorkflowFinding,
    _add_finding,
    build_workflow_issue_recommendation,
    detect_github_actions_security_issues,
    extract_workflow_issue_line,
)
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions

RESOURCES_DIR = Path(__file__).parent.joinpath("resources")


@pytest.mark.parametrize(
    "workflow_path",
    [
        "injection_pattern_1.yaml",
    ],
)
def test_detect_github_actions_security_issues(
    snapshot: list[WorkflowFinding], workflow_path: str, github_actions_service: GitHubActions
) -> None:
    """Test GH Actions workflows injection patterns."""
    callgraph = github_actions_service.build_call_graph_for_files(
        [os.path.join(RESOURCES_DIR, "workflow_files", workflow_path)],
        repo_path=os.path.join(RESOURCES_DIR, "workflow_files"),
    )
    assert detect_github_actions_security_issues(callgraph) == snapshot


def test_extract_workflow_issue_line_from_potential_injection() -> None:
    """Extract the source line from a potential-injection issue payload."""
    issue = (
        "potential-injection: "
        "[{'Type': 'Lit', 'Pos': {'Offset': 269, 'Line': 6, 'Col': 48}, 'Value': 'origin/'}, "
        "{'Type': 'ParamExp', 'Pos': {'Offset': 276, 'Line': 6, 'Col': 55}}]"
    )

    assert extract_workflow_issue_line(issue) == 6


def test_extract_workflow_issue_line_prefers_step_line_marker() -> None:
    """Extract the workflow line from an explicit step-line marker."""
    issue = (
        "potential-injection: "
        "[step-line=14] "
        "[{'Type': 'Lit', 'Pos': {'Offset': 269, 'Line': 6, 'Col': 48}, 'Value': 'origin/'}]"
    )

    assert extract_workflow_issue_line(issue) == 14


def test_extract_workflow_issue_line_from_structured_payload() -> None:
    """Extract workflow line from structured potential-injection payload."""
    issue = (
        "potential-injection: "
        '{"step_line": 62, "script_line": 6, "job": "retag", "step": "Retag", '
        '"command": "git push origin/${github.head_ref}", "parts": []}'
    )

    assert extract_workflow_issue_line(issue) == 62


def test_build_workflow_issue_recommendation_formats_potential_injection_details() -> None:
    """Format concise user-facing details for potential-injection findings."""
    issue = (
        "potential-injection: "
        '{"step_line": 62, "script_line": 6, "job": "retag", "step": "Retag", '
        '"command": "git push origin/${github.head_ref}", "parts": []}'
    )

    finding_type, _, finding_message = build_workflow_issue_recommendation(issue)

    assert finding_type == "potential-injection"
    assert "Unsafe expansion of attacker-controllable GitHub context can enable command injection." in finding_message
    assert "Details: Job: retag Step: Retag Command: `git push origin/${github.head_ref}`" in finding_message


def test_build_workflow_issue_recommendation_includes_expanded_refs() -> None:
    """Render expanded GitHub refs in potential-injection details when present."""
    issue = (
        "potential-injection: "
        '{"step_line": 62, "script_line": 6, "job": "retag", "step": "Retag", '
        '"command": "git push origin/${github.head_ref}", "expanded_refs": ["github.head_ref"]}'
    )

    _, _, finding_message = build_workflow_issue_recommendation(issue)

    assert "Expanded refs: `github.head_ref`" in finding_message


def test_build_workflow_issue_recommendation_includes_refs_from_compound_expression() -> None:
    """Render extracted github refs when original expression contains operators."""
    issue = (
        "potential-injection: "
        '{"step_line": 62, "script_line": 6, "job": "retag", "step": "Retag", '
        '"command": "git push origin/${github.head_ref}", '
        '"expanded_refs": ["github.head_ref", "github.ref_name"]}'
    )

    _, _, finding_message = build_workflow_issue_recommendation(issue)

    assert "Expanded refs: `github.head_ref, github.ref_name`" in finding_message


def test_build_workflow_issue_recommendation_formats_remote_script_exec_details() -> None:
    """Format concise user-facing details for remote-script-exec findings."""
    issue = (
        "remote-script-exec: "
        '{"step_line": 24, "script_line": 3, "job": "build", "step": "Setup", '
        '"command": "curl -fsSL https://x | bash"}'
    )

    finding_type, _, finding_message = build_workflow_issue_recommendation(issue)

    assert finding_type == "remote-script-exec"
    assert "Workflow downloads and executes remote scripts inline." in finding_message
    assert "Details: Job: build Step: Setup Command: `curl -fsSL https://x | bash`" in finding_message


def test_extract_workflow_issue_line_from_remote_script_exec_payload() -> None:
    """Extract workflow line from structured remote-script-exec payload."""
    issue = (
        "remote-script-exec: "
        '{"step_line": 24, "script_line": 3, "job": "build", "step": "Setup", '
        '"command": "curl -fsSL https://x | bash"}'
    )

    assert extract_workflow_issue_line(issue) == 24


def test_extract_workflow_issue_line_from_unpinned_action_marker() -> None:
    """Extract workflow line from unpinned action issue marker."""
    issue = "unpinned-third-party-action: [step-line=62] actions/checkout@v4.2.2"

    assert extract_workflow_issue_line(issue) == 62


def test_add_finding_deduplicates_and_preserves_highest_priority() -> None:
    """Keep one finding entry per issue and retain the highest priority."""
    findings: list[PrioritizedIssue] = []
    _add_finding(findings, "remote-script-exec: {}", 80)
    _add_finding(findings, "remote-script-exec: {}", 60)
    _add_finding(findings, "remote-script-exec: {}", 100)

    assert findings == [{"issue": "remote-script-exec: {}", "priority": 100}]
