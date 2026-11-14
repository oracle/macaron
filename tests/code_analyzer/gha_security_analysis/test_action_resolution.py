# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Workflow-scoped pinning resolution and recorded dependency traversal."""

import json
from pathlib import Path

import pytest

from macaron.code_analyzer.gha_security_analysis.action_resolution import (
    reachable_locked_dependencies,
    resolve_action_reference,
)
from macaron.parsers.github_actions_lockfile import ActionsLockfileError, parse_actions_lockfile
from tests.parsers.test_github_actions_lockfile import write_lockfile


@pytest.mark.parametrize(
    ("workflow", "uses", "method", "commit"),
    [
        (".github/workflows/ci.yml", "EXAMPLE/Parent/sub@v1", "lockfile", "a" * 40),
        (".github/workflows/other.yml", "example/parent@v1", "none", None),
        (".github/workflows/ci.yml", "example/orphan@v2", "none", None),
        (".github/workflows/ci.yml", "example/child@Main", "lockfile", "b" * 40),
        (".github/workflows/ci.yml", "example/child@main", "none", None),
        (".github/workflows/ci.yml", "$/actions/build", "same_repository", None),
        (".github/workflows/ci.yml", "./actions/build", "none", None),
        (".github/workflows/ci.yml", "docker://alpine:latest", "none", None),
        (".github/workflows/ci.yml", "example/other@" + "d" * 40, "inline_sha", "d" * 40),
    ],
)
def test_workflow_scope(tmp_path: Path, workflow: str, uses: str, method: str, commit: str | None) -> None:
    """Only applicable reachable entries grant lockfile pinning."""
    lockfile = parse_actions_lockfile(write_lockfile(tmp_path))
    result = resolve_action_reference(workflow, uses, lockfile)
    assert result.pinning_method == method
    assert result.resolved_commit == commit


def test_reusable_call_is_not_locked(tmp_path: Path) -> None:
    """Caller lockfiles never pin remote reusable workflows."""
    lockfile = parse_actions_lockfile(write_lockfile(tmp_path))
    result = resolve_action_reference(".github/workflows/ci.yml", "example/parent@v1", lockfile, reusable_workflow=True)
    assert result.pinning_method == "none"


def test_graph_preserves_chain_and_skips_orphans(tmp_path: Path) -> None:
    """Recorded child actions are scanned under their originating workflow."""
    lockfile = parse_actions_lockfile(write_lockfile(tmp_path))
    assert lockfile is not None
    uses = reachable_locked_dependencies(".github/workflows/ci.yml", lockfile)
    assert [(use.key, use.chain) for use in uses] == [
        ("example/child@Main", ("example/parent@v1", "example/child@Main")),
        ("example/parent@v1", ("example/parent@v1",)),
    ]


@pytest.mark.parametrize("child", ["example/missing@v2", "example/parent@v1"])
def test_broken_graph(tmp_path: Path, child: str) -> None:
    """Missing dependency entries and cycles are diagnosed conservatively."""
    path = write_lockfile(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["dependencies"]["example/parent@v1"]["uses"] = [child]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ActionsLockfileError):
        parse_actions_lockfile(path)
