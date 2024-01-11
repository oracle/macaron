# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the compare VSA script."""

import pytest

from macaron.util import JsonType
from tests.vsa.compare_vsa import compare_json, skip_compare


@pytest.mark.parametrize(
    ("result_value", "expected_value"),
    [
        pytest.param(
            "1",
            1,
            id="Different types of value 1",
        ),
        pytest.param(
            1,
            "1",
            id="Different types of value 2",
        ),
        pytest.param(
            [],
            {},
            id="Different types of value 3",
        ),
        pytest.param(
            {},
            [],
            id="Different types of value 4",
        ),
        pytest.param(
            [1, 3],
            [1, 2, 3],
            id="Array missing a field",
        ),
        pytest.param(
            [1, 2, 3],
            [1, 3],
            id="Array having extraneous field",
        ),
        pytest.param(
            {
                "foo": 1,
                "bar": 2,
            },
            {
                "foo": 1,
            },
            id="Object missing a field",
        ),
        pytest.param(
            {
                "baz": {
                    "foo": 1,
                    "bar": 2,
                },
            },
            {
                "baz": {
                    "foo": 1,
                },
            },
            id="Nested object missing a field",
        ),
        pytest.param(
            {
                "foo": 1,
            },
            {
                "foo": 1,
                "bar": 2,
            },
            id="Object containing extraneous field",
        ),
        pytest.param(
            {
                "baz": {
                    "foo": 1,
                },
            },
            {
                "baz": {
                    "foo": 1,
                    "bar": 2,
                },
            },
            id="Nested object containing extraneous field",
        ),
    ],
)
def test_compare_json_fails(result_value: JsonType, expected_value: JsonType) -> None:
    """Test cases where compare should fail."""
    assert (
        compare_json(
            result=result_value,
            expected=expected_value,
            compare_fn_map={},
        )
        is False
    )


@pytest.mark.parametrize(
    ("result_value", "expected_value", "skipped_field_name"),
    [
        pytest.param(
            {
                "foo": "foo",
            },
            {
                "foo": "bar",
            },
            ".foo",
            id="Top-level object field",
        ),
        pytest.param(
            {
                "foo": {"bar": "bar"},
            },
            {
                "foo": {"bar": "baz"},
            },
            ".foo.bar",
            id="Nested object field",
        ),
        pytest.param(
            {
                "foo": [0, 1, 2],
            },
            {
                "foo": [0, 99, 2],
            },
            ".foo[1]",
            id="Array field",
        ),
        pytest.param(
            {
                "foo": [
                    ["bar1"],
                    ["bar2a", "bar2b"],
                    ["bar3"],
                ],
            },
            {
                "foo": [
                    ["bar1"],
                    ["foobar", "bar2b"],
                    ["bar3"],
                ],
            },
            ".foo[1][0]",
            id="Nested array field",
        ),
    ],
)
def test_skip_compare(
    result_value: JsonType,
    expected_value: JsonType,
    skipped_field_name: str,
) -> None:
    """Test cases where compare should succeed while skipping certain fields."""
    assert (
        compare_json(
            result=result_value,
            expected=expected_value,
            compare_fn_map={
                skipped_field_name: skip_compare,
            },
        )
        is True
    )
