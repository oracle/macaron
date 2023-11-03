# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for helper functions related to environment variables."""

import pytest

from macaron.environment_variables import get_patched_env


@pytest.mark.parametrize(
    ("before", "patch", "expect"),
    [
        pytest.param(
            {"FOO": "some-value"},
            {},
            {"FOO": "some-value"},
            id="patch is empty",
        ),
        pytest.param(
            {"FOO": "some-value"},
            {"GIT_TERMINAL_PROMPT": "0"},
            {
                "FOO": "some-value",
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
    expect: dict[str, str],
) -> None:
    """Tests for the ``get_patched_env`` helper function."""
    env = dict(before)

    assert get_patched_env(patch, env) == expect
