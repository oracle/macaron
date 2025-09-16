# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the base_cli_options.py module."""

from collections.abc import Mapping
from typing import Any

import pytest

from macaron.build_spec_generator.cli_command_parser import (
    is_dict_of_str_to_str_or_none,
    is_list_of_strs,
    patch_mapping,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(
            {"A": "B"},
            True,
        ),
        pytest.param(
            {"A": None, "B": "C"},
            True,
        ),
        pytest.param(
            {"A": "B", "C": "D"},
            True,
        ),
        pytest.param(
            True,
            False,
        ),
        pytest.param(
            ["A", "B"],
            False,
        ),
        pytest.param(
            {"A": "B", "C": 1, "D": {}},
            False,
        ),
        pytest.param(
            {1: "B"},
            False,
        ),
    ],
)
def test_is_dict_of_str_to_str_or_none(value: Any, expected: bool) -> None:
    """Test the is_dict_of_str_to_str_or_none type guard."""
    assert is_dict_of_str_to_str_or_none(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(
            ["str1", "str2"],
            True,
        ),
        pytest.param(
            [],
            True,
        ),
        pytest.param(
            {"A": "B"},
            False,
        ),
        pytest.param(
            "str",
            False,
        ),
        pytest.param(
            True,
            False,
        ),
    ],
)
def test_is_list_of_strs(value: Any, expected: bool) -> None:
    """Test the is_list_of_strs function."""
    assert is_list_of_strs(value) == expected


@pytest.mark.parametrize(
    ("original", "patch", "expected"),
    [
        pytest.param(
            {},
            {},
            {},
        ),
        pytest.param(
            {"boo": "foo", "bar": "far"},
            {},
            {"boo": "foo", "bar": "far"},
        ),
        pytest.param(
            {},
            {"boo": "foo", "bar": "far"},
            {"boo": "foo", "bar": "far"},
        ),
        pytest.param(
            {"boo": "foo", "bar": "far"},
            {"boo": "another_foo"},
            {"boo": "another_foo", "bar": "far"},
        ),
        pytest.param(
            {"boo": "foo", "bar": "far"},
            {"boo": "another_foo", "bar": None},
            {"boo": "another_foo"},
            id="Use None to remove a system property",
        ),
    ],
)
def test_patch_mapping(
    original: Mapping[str, str],
    patch: Mapping[str, str | None],
    expected: Mapping[str, str],
) -> None:
    """Test the patch mapping function."""
    assert (
        patch_mapping(
            original=original,
            patch=patch,
        )
        == expected
    )
