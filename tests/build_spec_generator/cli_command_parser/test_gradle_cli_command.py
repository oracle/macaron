# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains tests for the gradle_cli_command module."""


import pytest

from macaron.build_spec_generator.cli_command_parser.gradle_cli_command import GradleCLIOptions
from macaron.build_spec_generator.cli_command_parser.gradle_cli_parser import GradleCLICommandParser


@pytest.mark.parametrize(
    ("this", "that"),
    [
        pytest.param(
            "gradle",
            "gradle",
            id="test_equal_only_executable",
        ),
        pytest.param(
            "gradlew -S clean build -x test",
            "gradlew clean build -S -x test",
            id="test_different_order_of_options",
        ),
        pytest.param(
            "gradlew clean build -Pgnupg.skip -Pskip.signing",
            "gradlew clean build -Pskip.signing -Pgnupg.skip ",
            id="test_properties_equal_checking",
        ),
        pytest.param(
            "gradlew clean build -Dorg.gradle.caching=true -PmyProperty=boo",
            "gradlew clean build -Dorg.gradle.caching=true -PmyProperty=boo",
            id="test_properties_with_values_equal_checking",
        ),
        pytest.param(
            "gradlew clean build -x test -x boo",
            "gradlew clean build -x test -x boo",
            id="test_excluded_tasks",
        ),
        pytest.param(
            "gradlew clean -x test -x boo build",
            "gradlew clean build -x test -x boo",
            id="test_intermixed_args",
        ),
    ],
)
def test_comparing_gradle_cli_command_equal(
    gradle_cli_parser: GradleCLICommandParser,
    this: str,
    that: str,
) -> None:
    """Test comparing two equal GradleCLICommand objects."""
    this_command = gradle_cli_parser.parse(this.split())
    that_command = gradle_cli_parser.parse(that.split())
    assert this_command == that_command


@pytest.mark.parametrize(
    ("this", "that"),
    [
        ("gradle clean build", "gradle clean"),
        ("gradle", "gradlew"),
        ("gradle clean build", "gradle clean build -PmyProperty=true"),
        ("gradle clean build -Dorg.gradle.caching=true", "gradle clean build -Dorg.gradle.caching=false"),
        ("gradle clean build -Dorg.gradle.caching=true", "gradle clean build -Dorg.gradle.caching"),
        ("gradle clean build", "gradle clean build -c settings.gradle"),
        ("gradle build", "gradle build -x test"),
        # We persist the order which the task names are put into the excluded list.
        # Therefore the order of the -x options is important.
        ("gradle build -x test -x boo", "gradle build -x boo -x test"),
        ("gradle build --no-build-cache", "gradle build --build-cache"),
    ],
)
def test_comparing_gradle_cli_command_unequal(
    gradle_cli_parser: GradleCLICommandParser,
    this: str,
    that: str,
) -> None:
    """Test comparing two unequal GradleCLICommand objects."""
    this_command = gradle_cli_parser.parse(this.split())
    that_command = gradle_cli_parser.parse(that.split())
    assert not this_command == that_command


@pytest.mark.parametrize(
    ("command"),
    [
        "gradle clean build -x test --debug --stacktrace -Dorg.gradle.caching=true",
        "gradle",
        "gradle --version",
        "gradle -?",
        "gradlew --build-cache --continue --no-scan",
        "gradlew --build-cache --no-build-cache",
    ],
)
def test_to_cmd_goals(gradle_cli_parser: GradleCLICommandParser, command: str) -> None:
    """Test the to_cmd_goals method by print out the cmds and the parse it again."""
    gradle_cli_command = gradle_cli_parser.parse(command.split())

    print_command_with_tasks = [gradle_cli_command.executable]
    print_command_with_tasks.extend(gradle_cli_command.options.to_option_cmds())

    gradle_cli_command_second = gradle_cli_parser.parse(print_command_with_tasks)
    assert gradle_cli_command == gradle_cli_command_second


@pytest.mark.parametrize(
    ("properties", "expected"),
    [
        pytest.param(
            ["org.gradle.caching.debug=false", "boo=foo"],
            {"org.gradle.caching.debug": "false", "boo": "foo"},
        ),
        pytest.param(
            ["org.gradle.caching.debug=false", "org.gradle.caching.debug=true"],
            {"org.gradle.caching.debug": "true"},
            id="test_overriding_behavior_from_input",
        ),
        pytest.param(
            ["org.gradle.caching.debug=false", "boo"],
            {"org.gradle.caching.debug": "false", "boo": ""},
            id="test_property_default_value",
        ),
    ],
)
def test_gradle_cli_option_parse_properties(
    properties: list[str],
    expected: dict[str, str],
) -> None:
    """Test the GradleCLIOptions.parse_properties method."""
    assert GradleCLIOptions.parse_properties(properties) == expected
