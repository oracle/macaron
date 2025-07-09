# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Gradle CLI Parser."""

import pytest

from macaron.build_spec_generator.cli_command_parser.gradle_cli_parser import GradleCLICommandParser
from macaron.errors import CommandLineParseError


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        # Gradle doesn't raise error when you run it like this.
        # This is because when you provide no option, it still runs a task called ":help" to
        # print out the usage message.
        pytest.param(
            "gradle",
            {"tasks": []},
            id="can_run_gradle_without_any_option",
        ),
        pytest.param(
            "gradle -?",
            {"tasks": [], "help_": True},
            id="gradle_print_help_-?",
        ),
        pytest.param(
            "gradle --help",
            {"tasks": [], "help_": True},
            id="gradle_print_help_--help",
        ),
        pytest.param(
            "gradle -h",
            {"tasks": [], "help_": True},
            id="gradle_print_help_-h",
        ),
        pytest.param(
            "gradle --version",
            {"tasks": [], "version": True},
            id="gradle_print_version_long",
        ),
        pytest.param(
            "gradle -v",
            {"tasks": [], "version": True},
            id="gradle_print_version_short",
        ),
        pytest.param(
            "gradle clean build",
            {"tasks": ["clean", "build"]},
            id="gradle_tasks",
        ),
        pytest.param(
            "gradlew clean build",
            {"tasks": ["clean", "build"]},
            id="gradle_wrapper_tasks",
        ),
        pytest.param(
            "gradle clean build --continue",
            {"tasks": ["clean", "build"], "continue_": True},
            id="test_continue_flag_with_exception_in_attribute_name",
        ),
        # TODO: validate if the order of the options decide the final value of
        # the negateable option.
        # For example: `--build-cache --no-build-cache` is different from `--no-build-cache --build-cache`
        pytest.param(
            "gradle clean build --build-cache --no-build-cache",
            {"tasks": ["clean", "build"], "build_cache": False},
            id="both_normal_and_negated_form_can_be_provided_final_false",
        ),
        pytest.param(
            "gradle clean build --no-build-cache --build-cache",
            {"tasks": ["clean", "build"], "build_cache": True},
            id="both_normal_and_negated_form_can_be_provided_final_true",
        ),
        # This doesn't well represent a real gradle CLI command.
        # It's just for the purpose of unit testing.
        pytest.param(
            "gradle clean build --continue --debug --rerun-tasks -s --console plain --build-cache",
            {
                "tasks": ["clean", "build"],
                "continue_": True,
                "debug": True,
                "rerun_tasks": True,
                "stacktrace": True,
                "console": "plain",
                "build_cache": True,
            },
            id="combination_of_option_types",
        ),
    ],
)
def test_gradle_cli_command_parser_valid_input(
    gradle_cli_parser: GradleCLICommandParser,
    command: str,
    expected: dict[str, str | None | bool | list[str]],
) -> None:
    """Test the gradle cli parser on valid input."""
    parsed_res = gradle_cli_parser.parse(command.split())

    all_attrs = vars(parsed_res.options).keys()

    for attribute in all_attrs:
        if attribute in expected:
            assert getattr(parsed_res.options, attribute) == expected[attribute]
        else:
            # Making sure that we are not enabling flags that are not part of the
            # build command.
            # We don't compare it to None because some options if not set, argparse
            # will assign a different Falsy value depending on the option type.
            assert not getattr(parsed_res.options, attribute)


@pytest.mark.parametrize(
    ("build_command", "expected"),
    [
        pytest.param(
            "gradle clean build --debug --stacktrace",
            "gradle",
        ),
        pytest.param(
            "./gradlew clean build --debug --stacktrace",
            "./gradlew",
        ),
        pytest.param(
            "./boo/gradlew clean build --debug --stacktrace",
            "./boo/gradlew",
        ),
    ],
)
def test_gradle_cli_command_parser_executable(
    gradle_cli_parser: GradleCLICommandParser,
    build_command: str,
    expected: str,
) -> None:
    """Test the Gradle CLI command parser correctly persisting the executable string."""
    parse_res = gradle_cli_parser.parse(build_command.split())
    assert parse_res.executable == expected


@pytest.mark.parametrize(
    ("build_command"),
    [
        pytest.param("", id="An empty command"),
        pytest.param(
            "gradle --this-argument-should-never-exist-in-gradle",
            id="unrecognized_optional_argument",
        ),
        pytest.param(
            "gradle --this-argument-should-never-exist-in-gradle some-value",
            id="unrecognized_value_option",
        ),
        pytest.param(
            "./graaadddllewww clean build",
            id="unrecognized_executable_path",
        ),
    ],
)
def test_gradle_cli_command_parser_invalid_input(
    gradle_cli_parser: GradleCLICommandParser,
    build_command: str,
) -> None:
    """Test the Gradle CLI command parser on invalid input."""
    with pytest.raises(CommandLineParseError):
        gradle_cli_parser.parse(build_command.split())
