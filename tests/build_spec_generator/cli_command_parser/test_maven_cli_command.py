# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains tests for the maven_cli_command module."""

from typing import Any

import pytest

from macaron.build_spec_generator.cli_command_parser.maven_cli_command import MavenCLIOptions
from macaron.build_spec_generator.cli_command_parser.maven_cli_parser import MavenCLICommandParser


@pytest.mark.parametrize(
    ("this", "that"),
    [
        pytest.param(
            "mvn clean package",
            "mvn clean package",
            id="totally_equal",
        ),
        pytest.param(
            "mvn -X clean package -P project1,project2",
            "mvn clean package -X -P project1,project2",
            id="test_different_order_of_options",
        ),
        pytest.param(
            "mvn clean package -Dmaven.skip.test=true",
            "mvn clean package -Dmaven.skip.test",
            id="test_default_value_for_system_property",
        ),
    ],
)
def test_comparing_maven_cli_command_equal(
    maven_cli_parser: MavenCLICommandParser,
    this: str,
    that: str,
) -> None:
    """Test comparing two equal MavenCLICommand objects."""
    this_command = maven_cli_parser.parse(this.split())
    that_command = maven_cli_parser.parse(that.split())
    assert this_command == that_command


@pytest.mark.parametrize(
    ("this", "that"),
    [
        ("mvn clean package", "mvn install"),
        ("mvn clean package", "mvn clean package -X"),
        ("mvn clean package", "mvn clean package -P project1,project2"),
        ("mvn clean package", "mvn clean package -Dmaven.skip.test=true"),
        ("mvn clean package", "mvn clean package --settings ./pom.xml"),
        ("mvn clean package", "mvn package clean"),
        ("mvn clean package", "mvnw clean package"),
    ],
)
def test_comparing_maven_cli_command_unequal(
    maven_cli_parser: MavenCLICommandParser,
    this: str,
    that: str,
) -> None:
    """Test comparing two unequal MavenCLICommand objects."""
    this_command = maven_cli_parser.parse(this.split())
    that_command = maven_cli_parser.parse(that.split())
    assert not this_command == that_command


@pytest.mark.parametrize(
    ("command", "that"),
    [
        (
            "mvn clean package -P profile1,profile2 -T 2C -ntp -Dmaven.skip.test=true -Dboo=foo",
            True,
        ),
        (
            "mvn clean package -P profile1,profile2 -T 2C -ntp -Dmaven.skip.test=true -Dboo=foo",
            ["boo", "foo"],
        ),
        (
            "mvn clean package -P profile1,profile2 -T 2C -ntp -Dmaven.skip.test=true -Dboo=foo",
            {"boo", "foo"},
        ),
    ],
)
def test_comparing_maven_cli_command_unequal_types(
    maven_cli_parser: MavenCLICommandParser,
    command: str,
    that: Any,
) -> None:
    """Test comparing MavenCLICommand with another incompatible type oject."""
    this_command = maven_cli_parser.parse(command.split())
    assert not this_command == that


@pytest.mark.parametrize(
    ("command"),
    [
        "mvn clean package",
        "mvn clean package -P profile1,profile2 -T 2C -ntp -Dmaven.skip.test=true -Dboo=foo",
        "mvn -f fit/core-reference/pom.xml verify -Dit.test=RESTITCase -Dinvoker.streamLogs=true"
        + " -Dmodernizer.skip=true -Drat.skip=true -Dcheckstyle.skip=true -Djacoco.skip=true",
        "mvn -s ../.github/maven-settings.xml install -Pexamples,noRun",
        "mvn clean package -Dmaven.test.skip",
    ],
)
def test_to_cmd_goals(maven_cli_parser: MavenCLICommandParser, command: str) -> None:
    """Test the to_cmd_goals method by print out the cmds and the parse it again."""
    maven_cli_command = maven_cli_parser.parse(command.split())

    print_command_with_goals = [maven_cli_command.executable]
    print_command_with_goals.extend(maven_cli_command.options.to_option_cmds())

    maven_cli_command_second = maven_cli_parser.parse(print_command_with_goals)
    assert maven_cli_command == maven_cli_command_second


@pytest.mark.parametrize(
    ("properties", "expected"),
    [
        pytest.param(
            ["maven.skip.true=true", "boo=foo"],
            {"maven.skip.true": "true", "boo": "foo"},
        ),
        pytest.param(
            ["maven.skip.true=true", "maven.skip.true=false", "maven.skip.true=true"],
            {"maven.skip.true": "true"},
            id="test_overriding_behavior_from_input",
        ),
        pytest.param(
            # For example one can specify mvn clean package -Dmaven.skip.true=true -Dboo
            ["maven.skip.true=true", "boo"],
            {"maven.skip.true": "true", "boo": "true"},
            id="test_system_property_default_value",
        ),
    ],
)
def test_maven_cli_option_parse_system_properties(
    properties: list[str],
    expected: dict[str, str],
) -> None:
    """Test the MavenCLIOptions.parse_system_properties method."""
    assert MavenCLIOptions.parse_system_properties(properties) == expected
