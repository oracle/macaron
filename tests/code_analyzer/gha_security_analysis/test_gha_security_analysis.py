# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for GitHub Actions security analysis detection heuristics."""

import os
from pathlib import Path

import pytest

from macaron.code_analyzer.gha_security_analysis.detect_injection import detect_github_actions_security_issues
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions

RESOURCES_DIR = Path(__file__).parent.joinpath("resources")


@pytest.mark.parametrize(
    "workflow_path",
    [
        "injection_pattern_1.yaml",
    ],
)
def test_detect_github_actions_security_issues(
    snapshot: dict, workflow_path: str, github_actions_service: GitHubActions
) -> None:
    """Test GH Actions workflows injection patterns."""
    callgraph = github_actions_service.build_call_graph_for_files(
        [os.path.join(RESOURCES_DIR, "workflow_files", workflow_path)],
        repo_path=os.path.join(RESOURCES_DIR, "workflow_files"),
    )
    assert detect_github_actions_security_issues(callgraph) == snapshot
