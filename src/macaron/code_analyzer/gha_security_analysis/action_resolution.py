# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Resolve action identity using only the owning repository's recorded lockfile."""

import re
from collections import deque
from dataclasses import dataclass
from typing import Literal

from macaron.errors import ActionsLockfileError
from macaron.parsers.github_actions_lockfile import (
    ActionsLockfile,
    LockedAction,
    canonical_action_key,
    validate_dependency_graph,
)

PinningMethod = Literal["inline_sha", "lockfile", "same_repository", "none"]
ActionKind = Literal["remote", "workspace", "same_repository", "container", "reusable"]


@dataclass(frozen=True)
class ActionResolution:
    """Declared reference and effective revision, with the source of pinning evidence."""

    declared_reference: str
    action_kind: ActionKind
    resolved_commit: str | None
    pinning_method: PinningMethod


@dataclass(frozen=True)
class LockedActionUse:
    """A reachable locked dependency and a deterministic originating call chain."""

    key: str
    action: LockedAction
    chain: tuple[str, ...]


def reachable_locked_dependencies(workflow_path: str, lockfile: ActionsLockfile) -> list[LockedActionUse]:
    """Validate a workflow's recorded graph and retain the shortest chain per dependency.

    Traverse iteratively to avoid Python recursion limits on untrusted graphs.
    Cycles and dangling edges are errors, not truncated successful coverage.
    """
    roots = lockfile.workflows.get(workflow_path, ())
    validate_dependency_graph(lockfile.dependencies, roots, f"{lockfile.path}: {workflow_path}")
    chains: dict[str, tuple[str, ...]] = {}
    pending: deque[tuple[str, ...]] = deque((root,) for root in sorted(roots))
    while pending:
        chain = pending.popleft()
        key = chain[-1]
        if key in chains and (len(chains[key]), chains[key]) <= (len(chain), chain):
            continue
        chains[key] = chain
        pending.extend((*chain, child) for child in sorted(lockfile.dependencies[key].uses))
    return [LockedActionUse(key, lockfile.dependencies[key], chains[key]) for key in sorted(chains)]


def resolve_action_reference(
    workflow_path: str,
    uses: str,
    lockfile: ActionsLockfile | None,
    *,
    reusable_workflow: bool = False,
) -> ActionResolution:
    """Classify raw uses syntax and credit only applicable recorded action pins."""
    if uses.startswith("./"):
        return ActionResolution(uses, "workspace", None, "none")
    if uses.startswith("$/"):
        return ActionResolution(uses, "same_repository", None, "same_repository")
    if uses.startswith("docker://"):
        return ActionResolution(uses, "container", None, "none")
    kind: ActionKind = "reusable" if reusable_workflow else "remote"
    key = canonical_action_key(uses, subpath=True)
    ref = key.partition("@")[2]
    resolved = None
    if lockfile is not None and not reusable_workflow:
        for dependency in reachable_locked_dependencies(workflow_path, lockfile):
            if dependency.key == key:
                if dependency.action.hostname != "github.com":
                    raise ActionsLockfileError(
                        f"{lockfile.path}: unsupported dependency host {dependency.action.hostname}"
                    )
                resolved = dependency.action.commit
                break
    if resolved is not None:
        return ActionResolution(uses, kind, resolved, "lockfile")
    if re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", ref):
        return ActionResolution(uses, kind, ref, "inline_sha")
    return ActionResolution(uses, kind, None, "none")
