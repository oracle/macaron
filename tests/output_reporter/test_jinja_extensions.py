# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This modules contains tests for the Jinja2 filter and test extensions.
"""


from hypothesis import given
from hypothesis import strategies as st

from macaron.output_reporter.jinja2_extensions import j2_filter_get_flatten_dict, j2_filter_get_headers

from ..macaron_testcase import MacaronTestCase
from ..st import RECURSIVE_DICT_ST, UN_NESTED_DICT_ST


def _check_is_flatten(input_dict: dict) -> bool:
    """Return False if the input dictionary uses list as one of its values."""
    result = True
    for value in input_dict.values():
        if isinstance(value, list):
            result = False
            break

        if isinstance(value, dict):
            result = _check_is_flatten(value)

    return result


class Jinja2ExtTest(MacaronTestCase):
    """Test the Jinja2 filter and test extensions."""

    @given(input_list=st.lists(UN_NESTED_DICT_ST, max_size=10))
    def test_get_headers(self, input_list: list[dict]) -> None:
        """Test the get_headers filter."""
        headers = j2_filter_get_headers(input_list)
        assert len(headers) == len(set(headers))
        for dictionary in input_list:
            for key in dictionary:
                assert key in headers

    @given(input_dict=RECURSIVE_DICT_ST)
    def test_get_flatten_dict(self, input_dict: dict) -> None:
        """Test the get_flatten_dict filter."""
        output = j2_filter_get_flatten_dict(input_dict)
        assert _check_is_flatten(output)
