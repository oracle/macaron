# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for GitHub Actions security recommendation helpers."""

import pytest

from macaron.code_analyzer.gha_security_analysis.recommendation import (
    recommend_for_unpinned_action,
    resolve_action_ref_to_tag,
)


def test_recommend_for_unpinned_action_with_tag_hint() -> None:
    """Return pinned action recommendation with tag hint when SHA and tag are resolved."""
    recommendation = recommend_for_unpinned_action(
        "actions/checkout",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "v4.2.2",
    )

    assert recommendation.recommended_ref == "actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa # v4.2.2"


def test_recommend_for_unpinned_action_when_sha_not_resolved() -> None:
    """Return fallback recommendation text when action SHA cannot be resolved."""
    recommendation = recommend_for_unpinned_action("actions/checkout")

    assert recommendation.recommended_ref == "cannot be found"
    assert recommendation.message == "Pin this third-party action to a 40-character commit SHA."


def test_resolve_action_ref_to_tag_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve the matching tag when a tag points to the resolved action SHA."""
    monkeypatch.setattr(
        "macaron.code_analyzer.gha_security_analysis.recommendation.get_tags_via_git_remote",
        lambda repo: {"v4.2.2": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
    )

    tag = resolve_action_ref_to_tag("actions/checkout", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "v4")

    assert tag == "v4.2.2"


def test_resolve_action_ref_to_tag_none_when_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return None when no fetched tag points to the resolved action SHA."""
    monkeypatch.setattr(
        "macaron.code_analyzer.gha_security_analysis.recommendation.get_tags_via_git_remote",
        lambda repo: {"v4.2.2": "dddddddddddddddddddddddddddddddddddddddd"},
    )

    tag = resolve_action_ref_to_tag("actions/checkout", "cccccccccccccccccccccccccccccccccccccccc", "v4")

    assert tag is None
