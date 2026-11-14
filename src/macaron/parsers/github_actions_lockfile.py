# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Read GA workflow lockfiles without executing dependency code.

Compatibility reference: github/actions-lockfile revision
54969dc7fee8b1e0e22b06bd4b591c44232f831c, go/pkg/lockfile.
This establishes recorded coverage, not upstream provenance verification.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ruamel.yaml import YAML, YAMLError

from macaron.errors import ActionsLockfileError

LOCKFILE_PATH = ".github/workflows/actions.lock"
MAX_LOCKFILE_SIZE = 1 << 20


@dataclass(frozen=True)
class LockedAction:
    """Validated metadata for one repository/ref pair."""

    ref: str
    commit: str
    owner_id: int
    repo_id: int
    hostname: str
    uses: tuple[str, ...]


@dataclass(frozen=True)
class ActionsLockfile:
    """Workflow membership and the recorded action graph."""

    path: Path
    workflows: dict[str, tuple[str, ...]]
    dependencies: dict[str, LockedAction]


def validate_dependency_graph(dependencies: dict[str, LockedAction], roots: Iterable[str], source: str) -> None:
    """Validate graph edges and acyclicity without recursion or loading action code.

    Three-state traversal distinguishes a dependency shared by different parents
    from a back edge. The parser validates the whole document; consumers may also
    validate a workflow scope for independently constructed typed records.
    """
    completed: set[str] = set()
    active: set[str] = set()
    for root in roots:
        stack = [(root, False)]
        while stack:
            key, leaving = stack.pop()
            if leaving:
                active.remove(key)
                completed.add(key)
                continue
            if key in active:
                raise ActionsLockfileError(f"{source}: dependency cycle at {key}")
            if key in completed:
                continue
            if key not in dependencies:
                raise ActionsLockfileError(f"{source}: missing dependency {key}")
            active.add(key)
            stack.append((key, True))
            stack.extend((child, False) for child in reversed(dependencies[key].uses))


def canonical_action_key(reference: str, *, subpath: bool = False) -> str:
    """Validate a remote pin, preserving ref case and optionally removing an action subpath."""
    repository, separator, ref = reference.partition("@")
    parts = repository.split("/")
    if not separator or len(parts) < 2 or (not subpath and len(parts) != 2):
        raise ActionsLockfileError(f"Invalid action reference: {reference!r}")
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part not in {".", ".."} for part in parts):
        raise ActionsLockfileError(f"Invalid action repository/path: {reference!r}")
    if not ref or any(character.isspace() or ord(character) < 32 for character in ref):
        raise ActionsLockfileError(f"Invalid action ref: {reference!r}")
    if any(character in ref for character in "@:^~?*[\\") or ".." in ref or ref.endswith(("/", ".")):
        raise ActionsLockfileError(f"Invalid action ref: {reference!r}")
    if re.fullmatch(r"[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64}", ref):
        ref = ref.lower()
    return f"{parts[0].lower()}/{parts[1].lower()}@{ref}"


def parse_actions_lockfile(path: Path) -> ActionsLockfile | None:
    """Load a bounded, strict v0.0.3 document; distinguish absence from invalid content.

    Only expected file/encoding/YAML errors become lockfile diagnostics. Programming
    errors propagate. Schema failures include the path and the affected field/key.
    """
    try:
        with path.open("rb") as stream:
            contents = stream.read(MAX_LOCKFILE_SIZE + 1)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ActionsLockfileError(f"{path}: cannot read lockfile: {error}") from error
    if len(contents) > MAX_LOCKFILE_SIZE:
        raise ActionsLockfileError(f"{path}: lockfile exceeds 1 MiB")
    try:
        yaml = YAML(typ="safe")
        yaml.allow_duplicate_keys = False
        document: object = yaml.load(contents.decode("utf-8"))
    except (YAMLError, UnicodeError) as error:
        raise ActionsLockfileError(f"{path}: invalid lockfile YAML: {error}") from error
    if not isinstance(document, dict):
        raise ActionsLockfileError(f"{path}: expected a lockfile mapping")
    data = cast(dict[str, object], document)
    if data.get("version") != "v0.0.3":
        raise ActionsLockfileError(f"{path}: unsupported lockfile version {data.get('version')!r}; supported: v0.0.3")
    if set(data) - {"version", "workflows", "dependencies"}:
        raise ActionsLockfileError(f"{path}: unknown lockfile fields")
    raw_workflows = data.get("workflows", {})
    raw_dependencies = data.get("dependencies", {})
    if not isinstance(raw_workflows, dict) or not isinstance(raw_dependencies, dict):
        raise ActionsLockfileError(f"{path}: workflows and dependencies must be mappings")

    workflows: dict[str, tuple[str, ...]] = {}
    for workflow, references in raw_workflows.items():
        if (
            not isinstance(workflow, str)
            or not workflow
            or workflow.startswith("/")
            or ".." in workflow.split("/")
            or any(char in workflow for char in "\\:")
            or any(ord(char) < 32 or ord(char) == 127 for char in workflow)
        ):
            raise ActionsLockfileError(f"{path}: invalid repository-relative workflow path {workflow!r}")
        if not isinstance(references, list) or not all(isinstance(ref, str) for ref in references):
            raise ActionsLockfileError(f"{path}: workflow {workflow!r} must list action references")
        workflows[workflow] = tuple(canonical_action_key(ref) for ref in references)

    dependencies: dict[str, LockedAction] = {}
    for reference, metadata in raw_dependencies.items():
        if not isinstance(reference, str) or not isinstance(metadata, dict):
            raise ActionsLockfileError(f"{path}: dependency entries must map references to metadata")
        key = canonical_action_key(reference)
        required = {"ref", "commit", "owner_id", "repo_id"}
        if not required <= set(metadata) or set(metadata) - required - {"hostname", "uses"}:
            raise ActionsLockfileError(f"{path}: {key}: missing required or unknown metadata fields")
        ref, commit = metadata["ref"], metadata["commit"]
        owner_id, repo_id = metadata["owner_id"], metadata["repo_id"]
        hostname, uses = metadata.get("hostname", "github.com"), metadata.get("uses", [])
        if not isinstance(ref, str) or not ref or not isinstance(commit, str):
            raise ActionsLockfileError(f"{path}: {key}: ref and commit must be non-empty strings")
        if not re.fullmatch(r"sha1-[A-Fa-f0-9]{40}|sha256-[A-Fa-f0-9]{64}", commit):
            raise ActionsLockfileError(f"{path}: {key}: invalid algorithm-prefixed commit")
        if (
            not isinstance(owner_id, int)
            or isinstance(owner_id, bool)
            or not isinstance(repo_id, int)
            or isinstance(repo_id, bool)
            or not 0 < owner_id < 2**63
            or not 0 < repo_id < 2**63
        ):
            raise ActionsLockfileError(f"{path}: {key}: repository IDs must be positive 64-bit integers")
        if not isinstance(hostname, str) or not re.fullmatch(
            r"github\.com|[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.ghe\.com", hostname
        ):
            raise ActionsLockfileError(f"{path}: {key}: invalid hostname")
        if not isinstance(uses, list) or not all(isinstance(child, str) for child in uses):
            raise ActionsLockfileError(f"{path}: {key}: uses must list action references")
        key_ref = key.partition("@")[2]
        digest = commit.partition("-")[2].lower()
        if re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", key_ref):
            if key_ref != digest:
                raise ActionsLockfileError(f"{path}: {key}: immutable ref disagrees with commit")
        elif key_ref != ref:
            raise ActionsLockfileError(f"{path}: {key}: metadata ref disagrees with dependency key")
        action = LockedAction(
            ref, digest, owner_id, repo_id, hostname, tuple(canonical_action_key(child) for child in uses)
        )
        if key in dependencies and dependencies[key] != action:
            raise ActionsLockfileError(f"{path}: conflicting canonical dependency {key}")
        dependencies[key] = action
    validate_dependency_graph(dependencies, dependencies, str(path))
    for workflow, references in workflows.items():
        validate_dependency_graph(dependencies, references, f"{path}: {workflow}")
    return ActionsLockfile(path, workflows, dependencies)
