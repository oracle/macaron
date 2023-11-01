# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for context managers related to environment variables."""

import pytest

from macaron.env import get_patched_env


@pytest.mark.parametrize(
    ("before", "patch", "after"),
    [
        pytest.param(
            {"PATH": "/usr/local/bin"},
            {},
            {"PATH": "/usr/local/bin"},
            id="patch is empty",
        ),
        pytest.param(
            {"PATH": "/usr/local/bin"},
            {"GIT_TERMINAL_PROMPT": "0"},
            {
                "PATH": "/usr/local/bin",
                "GIT_TERMINAL_PROMPT": "0",
            },
            id="patch adding a variable",
        ),
        pytest.param(
            {"GIT_TERMINAL_PROMPT": "1"},
            {"GIT_TERMINAL_PROMPT": "0"},
            {"GIT_TERMINAL_PROMPT": "0"},
            id="patch overriding a variable",
        ),
        pytest.param(
            {"GIT_TERMINAL_PROMPT": "0"},
            {"GIT_TERMINAL_PROMPT": None},
            {},
            id="patch removing a variable",
        ),
    ],
)
def test_patched_env(
    before: dict[str, str],
    patch: dict[str, str | None],
    after: dict[str, str],
) -> None:
    """Tests for the ``patched_env`` context manager."""
    env = dict(before)

    assert get_patched_env(patch, env) == after
