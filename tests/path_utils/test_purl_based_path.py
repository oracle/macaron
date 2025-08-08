# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the purl_based_path module."""

import pytest

from macaron.path_utils.purl_based_path import get_purl_based_dir


@pytest.mark.parametrize(
    ("purl_type", "purl_namespace", "purl_name", "expected"),
    [
        pytest.param(
            "maven",
            "oracle",
            "macaron",
            "maven/oracle/macaron",
            id="simple_case_with_no_special_characters",
        ),
        pytest.param(
            "maven",
            None,
            "macaron",
            "maven/macaron",
            id="no_namespace",
        ),
        pytest.param(
            "maven",
            "boo#bar",
            "macaron@oracle",
            "maven/boo_bar/macaron_oracle",
            id="handle_non_allow_chars",
        ),
        pytest.param(
            "maven",
            "boo123bar",
            "macaron123oracle",
            "maven/boo123bar/macaron123oracle",
            id="digits_are_allowed",
        ),
        pytest.param(
            "maven",
            "boo-bar",
            "macaron-oracle",
            "maven/boo-bar/macaron-oracle",
            id="dashes_are_allowed",
        ),
    ],
)
def test_get_purl_based_dir(
    purl_type: str,
    purl_namespace: str,
    purl_name: str,
    expected: str,
) -> None:
    """Test the get_purl_based_dir function."""
    assert (
        get_purl_based_dir(
            purl_type=purl_type,
            purl_name=purl_name,
            purl_namespace=purl_namespace,
        )
        == expected
    )
