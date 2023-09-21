# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the defaults module."""

import os

import pytest

from macaron.config.defaults import ConfigParser, create_defaults, defaults, load_defaults
from macaron.config.global_config import global_config


def test_load_defaults() -> None:
    """Test loading defaults."""
    config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "defaults.ini")

    # Test that the user configuration is loaded.
    assert load_defaults(config_dir) is True

    # Test that the values in user configuration is prioritized.
    assert defaults.get("dependency.resolver", "dep_tool_maven") == "cyclonedx-maven:1.1.1"

    # Test loading an invalid configuration path.
    assert load_defaults("invalid") is False


def test_create_defaults() -> None:
    """Test dumping the default values."""
    output_dir = os.path.dirname(os.path.abspath(__file__))
    assert create_defaults(output_dir, global_config.macaron_path) is True


@pytest.mark.parametrize(
    ("section", "item", "delimiter", "strip", "duplicated_ok", "expect"),
    [
        (
            "test.list",
            "commas_string",
            ",",
            False,
            True,
            ["", " gitlab.com", " space string", " space string", "github.com"],
        ),
        ("test.list", "commas_string", ",", False, False, ["", " gitlab.com", " space string", "github.com"]),
        ("test.list", "commas_string", ",", True, True, ["github.com", "gitlab.com", "space string", "space string"]),
        ("test.list", "commas_string", ",", True, False, ["github.com", "gitlab.com", "space string"]),
        # Using None as the delimiter parameter will ignore cleanup
        ("test.list", "default", None, True, False, ["comma_ended,", "github.com", "space", "string"]),
        ("test.list", "default", None, False, False, ["comma_ended,", "github.com", "space", "string"]),
        (
            "test.list",
            "default",
            None,
            False,
            True,
            ["comma_ended,", "github.com", "space", "space", "string", "string"],
        ),
        ("test.list", "one_line", None, True, False, ["comma_ended,", "github.com", "space", "string"]),
        (
            "test.list",
            "one_line",
            None,
            True,
            True,
            ["comma_ended,", "github.com", "space", "space", "string", "string"],
        ),
    ],
)
def test_get_str_list_with_custom_delimiter(
    section: str, item: str, delimiter: str, strip: bool, duplicated_ok: bool, expect: list[str]
) -> None:
    """Test getting a list of strings from defaults.ini using a custom delimiter."""
    content = """
    [test.list]
    default =
        github.com
        comma_ended,
        space string
        space string
    empty =
    one_line = github.com comma_ended, space string space string
    commas_string = ,github.com, gitlab.com, space string, space string
    """
    custom_defaults = ConfigParser()
    custom_defaults.read_string(content)

    results = custom_defaults.get_list(section, item, delimiter=delimiter, strip=strip, duplicated_ok=duplicated_ok)
    results.sort()
    assert results == expect


@pytest.mark.parametrize(
    ("section", "item", "strip", "duplicated_ok", "fallback", "expect"),
    [
        ("test.list", "default", True, False, [], ["comma_ended,", "github.com", "space string"]),
        ("test.list", "default", True, True, [], ["comma_ended,", "github.com", "space string", "space string"]),
        ("test.list", "empty", False, True, [], [""]),
        ("test.list", "empty", True, True, [], []),
        # Test for an item that does not exist in defaults.ini
        ("test.list", "item_not_exist", True, True, [], []),
        # Test value for fallback. The fallback value must be returned as is and shouldn't be modified by the method.
        ("test.list", "item_not_exist", True, True, ["", "fallback_val"], ["", "fallback_val"]),
    ],
)
def test_get_str_list_with_default_delimiter(
    section: str, item: str, strip: bool, duplicated_ok: bool, fallback: list[str], expect: list[str]
) -> None:
    """Test getting a list of strings from defaults.ini using the default delimiter."""
    content = """
    [test.list]
    default =
        github.com
        comma_ended,
        space string
        space string
    empty =
    """
    custom_defaults = ConfigParser()
    custom_defaults.read_string(content)

    results = custom_defaults.get_list(section, item, strip=strip, fallback=fallback, duplicated_ok=duplicated_ok)
    results.sort()
    assert results == expect
