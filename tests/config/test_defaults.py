# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the defaults module."""

import os
from pathlib import Path

import pytest

from macaron.config.defaults import create_defaults, defaults, load_defaults
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


@pytest.mark.xfail(
    os.geteuid() == 0,
    reason="Only effective for non-root users",
)
def test_create_defaults_without_permission() -> None:
    """Test dumping default config in cases where the user does not have write permission to the output location."""
    assert create_defaults(output_path="/", cwd_path="/") is False


@pytest.mark.parametrize(
    ("user_config_input", "delimiter", "strip", "expect"),
    [
        (
            """
            [test.list]
            list = ,github.com, gitlab.com, space string, space string
            """,
            ",",
            False,
            ["", "github.com", " gitlab.com", " space string"],
        ),
        (
            """
            [test.list]
            list = ,github.com, gitlab.com, space string, space string
            """,
            ",",
            True,
            ["github.com", "gitlab.com", "space string"],
        ),
        # Using None as the `delimiter` will also remove leading and trailing spaces of elements. Therefore,
        # the results must be the same whether `strip` is set to True or False.
        (
            """
            [test.list]
            list =
                github.com
                comma_ended,
                space string
                space string
            """,
            None,
            True,
            ["github.com", "comma_ended,", "space", "string"],
        ),
        (
            """
            [test.list]
            list =
                github.com
                comma_ended,
                space string
                space string
            """,
            None,
            False,
            ["github.com", "comma_ended,", "space", "string"],
        ),
    ],
)
def test_get_str_list_with_custom_delimiter(
    user_config_input: str,
    delimiter: str,
    strip: bool,
    expect: list[str],
    tmp_path: Path,
) -> None:
    """Test getting a list of strings from defaults.ini using a custom delimiter."""
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)
    load_defaults(user_config_path)

    results = defaults.get_list(section="test.list", option="list", delimiter=delimiter, strip=strip)
    assert results == expect


@pytest.mark.parametrize(
    ("user_config_input", "expect"),
    [
        (
            """
            [test.list]
            list = ,github.com, gitlab.com, space string, space string
            """,
            [",github.com, gitlab.com, space string, space string"],
        ),
        (
            """
            [test.list]
            list =
                github.com
                comma_ended,
                space string
                foo bar
                foo bar
                space string
            """,
            ["github.com", "comma_ended,", "space string", "foo bar"],
        ),
        (
            """
            [test.list]
            list =
            """,
            [],
        ),
    ],
)
def test_get_str_list_default(
    user_config_input: str,
    expect: list[str],
    tmp_path: Path,
) -> None:
    """Test default behavior of getting a list of strings from an option in defaults.ini.

    The default behavior includes striping leading/trailing whitespaces from elements, removing empty elements and
    removing duplicated elements from the return list.
    """
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)
    load_defaults(user_config_path)

    results = defaults.get_list(section="test.list", option="list")
    assert results == expect


@pytest.mark.parametrize(
    ("section", "option", "fallback", "expect"),
    [
        (
            "section",
            "non-existing",
            None,
            [],
        ),
        (
            "non-existing",
            "option",
            None,
            [],
        ),
        (
            "non-existing",
            "non-existing",
            None,
            [],
        ),
        (
            "section",
            "non-existing",
            ["some", "fallback", "value"],
            ["some", "fallback", "value"],
        ),
        (
            "non-existing",
            "option",
            ["some", "fallback", "value"],
            ["some", "fallback", "value"],
        ),
        (
            "non-existing",
            "non-existing",
            ["some", "fallback", "value"],
            ["some", "fallback", "value"],
        ),
    ],
)
def test_get_str_list_default_with_errors(
    section: str,
    option: str,
    fallback: list[str] | None,
    expect: list[str],
    tmp_path: Path,
) -> None:
    """Test errors from getting a list of string from defaults.ini."""
    content = """
    [section]
    option =
        github.com
        comma_ended,
        space string
        space string
    """
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(content)
    load_defaults(user_config_path)

    assert (
        defaults.get_list(
            section=section,
            option=option,
            fallback=fallback,
        )
        == expect
    )


@pytest.mark.parametrize(
    ("user_config_input", "expect"),
    [
        (
            """
            [test.list]
            list = ,github.com, gitlab.com, space string, space string
            """,
            [",github.com, gitlab.com, space string, space string"],
        ),
        (
            """
            [test.list]
            list =
                github.com
                comma_ended,
                space string
                foo bar
                foo bar
                space string
            """,
            ["github.com", "comma_ended,", "space string", "foo bar", "foo bar", "space string"],
        ),
        (
            """
            [test.list]
            list =
            """,
            [],
        ),
    ],
)
def test_get_str_list_default_duplicated_ok(
    user_config_input: str,
    expect: list[str],
    tmp_path: Path,
) -> None:
    """Test getting a list of strings from defaults.ini without removing duplicated elements."""
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)
    load_defaults(user_config_path)

    results = defaults.get_list(section="test.list", option="list", remove_duplicates=False)
    assert results == expect
