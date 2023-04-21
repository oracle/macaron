# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the defaults module."""

import os

from macaron.config.defaults import create_defaults, defaults, load_defaults
from macaron.config.global_config import global_config

from ..macaron_testcase import MacaronTestCase


class TestDefaults(MacaronTestCase):
    """This class includes tests for the defaults module."""

    def test_load_defaults(self) -> None:
        """Test loading defaults."""
        config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")
        assert load_defaults(config_dir) is True

        assert defaults.get("dependency.resolver", "dep_tool_maven") == "cyclonedx-maven:2.7.5"

    def test_create_defaults(self) -> None:
        """Test dumping the default values."""
        output_dir = os.path.dirname(os.path.abspath(__file__))
        assert create_defaults(output_dir, global_config.macaron_path) is True
        assert create_defaults("/", "/") is False

    def test_get_str_list(self) -> None:
        """Test getting a list of strings from defaults.ini"""
        content = """
        [test.list]
        with_new_lines =
            github.com
            comma_ended,
            space string
        empty =
        one_line = github.com comma_ended, space string
        duplicates =
            github.com github.com github.com
            github.com
        commas_string = github.com, gitlab.com, space string
        """
        defaults.read_string(content)
        expect = ["github.com", "comma_ended,", "space", "string"]
        expect.sort()

        # Parse a list defined in multiple lines.
        multiple_lines_values = defaults.get_list("test.list", "with_new_lines")
        multiple_lines_values.sort()

        # Parse a list defined in one line.
        one_line_values = defaults.get_list("test.list", "one_line")
        one_line_values.sort()

        assert len(multiple_lines_values) == len(one_line_values) == len(expect)
        for i, val in enumerate(expect):
            assert multiple_lines_values[i] == one_line_values[i] == val
            # Make sure that we are returning a list of strings.
            assert isinstance(multiple_lines_values[i], str)
            assert isinstance(one_line_values[i], str)

        # Parse a list with duplicated values.
        values_without_duplicates = defaults.get_list("test.list", "duplicates")
        assert len(values_without_duplicates) == 1
        assert values_without_duplicates == ["github.com"]

        # Parse an empty list.
        assert not defaults.get_list("test.list", "empty")

        # Trying to parse an item that does not exist in defaults.ini.
        assert not defaults.get_list("test.list", "item_not_exist")

        # Allow duplicated results
        values_with_duplicates = defaults.get_list("test.list", "duplicates", duplicated_ok=True)
        assert len(values_with_duplicates) == 4
        assert values_with_duplicates == ["github.com", "github.com", "github.com", "github.com"]

        # Split the strings using a delimiter
        expect_split_comma = ["github.com", " gitlab.com", " space string"]
        expect_split_comma.sort()

        values_split_with_comma = defaults.get_list("test.list", "commas_string", delimiter=",")
        values_split_with_comma.sort()
        assert len(values_split_with_comma) == 3
        assert values_split_with_comma == expect_split_comma
