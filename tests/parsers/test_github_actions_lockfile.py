# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Validate lockfiles without accepting ambiguous or incomplete dependency metadata."""

import json
from pathlib import Path

import pytest

from macaron.errors import ParseError
from macaron.parsers.github_actions_lockfile import ActionsLockfileError, parse_actions_lockfile


def write_lockfile(tmp_path: Path) -> Path:
    """Write a small GA-format graph with one nested dependency and an orphan."""
    path = tmp_path / "actions.lock"
    path.write_text(
        json.dumps(
            {
                "version": "v0.0.3",
                "workflows": {".github/workflows/ci.yml": ["Example/Parent@v1"]},
                "dependencies": {
                    "example/parent@v1": {
                        "ref": "v1",
                        "commit": "sha1-" + "a" * 40,
                        "owner_id": 1,
                        "repo_id": 2,
                        "uses": ["example/child@Main"],
                    },
                    "example/child@Main": {"ref": "Main", "commit": "sha1-" + "b" * 40, "owner_id": 1, "repo_id": 3},
                    "example/orphan@v2": {"ref": "v2", "commit": "sha1-" + "c" * 40, "owner_id": 1, "repo_id": 4},
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_parse_ga_lockfile(tmp_path: Path) -> None:
    """Repository names are canonicalized while symbolic refs retain case."""
    lockfile = parse_actions_lockfile(write_lockfile(tmp_path))
    assert lockfile is not None
    assert lockfile.workflows[".github/workflows/ci.yml"] == ("example/parent@v1",)
    assert lockfile.dependencies["example/child@Main"].commit == "b" * 40
    assert "example/child@main" not in lockfile.dependencies


def test_absent_lockfile(tmp_path: Path) -> None:
    """Absent lockfiles preserve normal SHA pinning behavior."""
    assert parse_actions_lockfile(tmp_path / "missing") is None


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "version: v99.0.0",
        "version: v0.0.3\nversion: v0.0.3",
        "[",
        "version: v0.0.3\nunknown: true",
        "version: v0.0.3\nworkflows: []",
    ],
)
def test_reject_invalid_document(tmp_path: Path, contents: str) -> None:
    """Present invalid files must not be treated as absent."""
    path = tmp_path / "actions.lock"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ActionsLockfileError):
        parse_actions_lockfile(path)
    assert issubclass(ActionsLockfileError, ParseError)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("commit", "sha1-deadbeef"),
        ("owner_id", True),
        ("repo_id", 0),
        ("ref", "wrong"),
        ("hostname", "https://github.com"),
        ("uses", "example/child@Main"),
        ("unknown", "field"),
    ],
)
def test_reject_invalid_dependency(tmp_path: Path, field: str, value: str | int | bool) -> None:
    """Malformed metadata must not grant pinning credit."""
    path = write_lockfile(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["dependencies"]["example/parent@v1"][field] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ActionsLockfileError):
        parse_actions_lockfile(path)


@pytest.mark.parametrize("field", ["ref", "commit", "owner_id", "repo_id"])
def test_required_metadata(tmp_path: Path, field: str) -> None:
    """Missing metadata cannot become a trusted pin."""
    path = write_lockfile(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["dependencies"]["example/parent@v1"][field]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ActionsLockfileError):
        parse_actions_lockfile(path)


def test_unreadable_lockfile_is_diagnostic(tmp_path: Path) -> None:
    """A directory in place of the file is an error, not missing coverage."""
    with pytest.raises(ActionsLockfileError):
        parse_actions_lockfile(tmp_path)


def test_graalvm_committed_fixture() -> None:
    """The exact reported commit's graph resolves Macaron and its nested upload action."""
    path = Path(__file__).parent / "resources/github_actions_lockfile/graalvm-actions.lock"
    lockfile = parse_actions_lockfile(path)
    assert lockfile is not None
    assert "oracle/macaron@v0.25.0" in lockfile.workflows[".github/workflows/macaron-check-github-actions.yml"]
    assert lockfile.dependencies["oracle/macaron@v0.25.0"].commit == "794eec32782979f577efb5ff71d585f683a3550f"
    assert len(lockfile.dependencies["oracle/macaron@v0.25.0"].uses) == 2


def test_invalid_orphan_cycle_is_not_accepted_as_valid_document(tmp_path: Path) -> None:
    """The supported parser rejects cycles even outside the currently analyzed workflow."""
    path = write_lockfile(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["dependencies"]["example/orphan@v2"]["uses"] = ["example/orphan@v2"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ActionsLockfileError, match="cycle"):
        parse_actions_lockfile(path)
