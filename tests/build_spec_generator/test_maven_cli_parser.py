# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for maven cli parser."""

from collections.abc import Mapping
from typing import Any

import pytest

from macaron.build_spec_generator.maven_cli_parser import (
    MavenCLICommandParseError,
    MavenCLICommandParser,
    is_dict_of_str_to_str,
    is_list_of_strs,
    patch_mapping,
)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        pytest.param(
            "mvn clean package",
            {"goals": ["clean", "package"]},
            id="No option, just goals",
        ),
        # https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html#Build_Lifecycle_Basics
        pytest.param(
            "mvn clean dependency:copy-dependencies package",
            {"goals": ["clean", "dependency:copy-dependencies", "package"]},
            id="A mixture of goals and phases",
        ),
        pytest.param(
            "mvn clean package -P profile1,profile2 -T 2C -ntp -Dmaven.skip.test=true -Dboo=foo",
            {
                "goals": ["clean", "package"],
                # "-P"
                "activate_profiles": ["profile1", "profile2"],
                # "-T"
                "threads": "2C",
                # "-ntp"
                "no_transfer_progress": True,
                # "-D<name>=<val>"
                "define": {"maven.skip.test": "true", "boo": "foo"},
            },
            id="Combination of goals, value option (threads), optional flag (no_transfer_progress), "
            "system property definition (define) and comma-delimited list of string (activate_profiles).",
        ),
        pytest.param(
            "mvn clean package -Dmaven.skip.test=true -Dmaven.skip.test=false",
            {
                "goals": ["clean", "package"],
                "define": {"maven.skip.test": "false"},
            },
            id="Allow overriding a system property by defining it multiple times.",
        ),
        # A modified version of
        # https://github.com/apache/syncope/blob/9437c6c978ca8c03b5e5cccc40a5a352be1ecc52/.github/workflows/crosschecks.yml#L70
        pytest.param(
            "mvn -f fit/core-reference/pom.xml verify -Dit.test=RESTITCase -Dinvoker.streamLogs=true "
            "-Dmodernizer.skip=true -Drat.skip=true -Dcheckstyle.skip=true -Djacoco.skip=true",
            {
                "file": "fit/core-reference/pom.xml",
                "goals": ["verify"],
                "define": {
                    "it.test": "RESTITCase",
                    "invoker.streamLogs": "true",
                    "modernizer.skip": "true",
                    "rat.skip": "true",
                    "checkstyle.skip": "true",
                    "jacoco.skip": "true",
                },
            },
            id="pkg:maven/org.apache.syncope.common.keymaster.self/syncope-common-keymaster-client-self@3.0.0",
        ),
        # https://github.com/apache/activemq-artemis/blob/2.27.1/.github/workflows/build.yml
        pytest.param(
            "mvn -s ../.github/maven-settings.xml install -Pexamples,noRun",
            {
                "settings": "../.github/maven-settings.xml",
                "goals": ["install"],
                "activate_profiles": ["examples", "noRun"],
            },
            id="pkg:maven/org.apache.activemq/artemis-log-annotation-processor@2.27.1",
        ),
    ],
)
def test_maven_cli_command_parser_valid_input(
    maven_cli_parser: MavenCLICommandParser,
    command: str,
    expected: dict[str, str | None | bool | list[str]],
) -> None:
    """Test the maven cli parser on valid input."""
    parsed_res = maven_cli_parser.parse(command.split())

    for key, val in expected.items():
        assert getattr(parsed_res.options, key) == val


@pytest.mark.parametrize(
    ("build_command", "expected"),
    [
        pytest.param(
            "mvn clean package -X -ntp",
            "mvn",
        ),
        pytest.param(
            "mvnw clean package -X -ntp",
            "mvnw",
        ),
        pytest.param(
            "./boo/mvnw clean package -X -ntp",
            "./boo/mvnw",
        ),
    ],
)
def test_maven_cli_command_parser_executable(
    maven_cli_parser: MavenCLICommandParser,
    build_command: str,
    expected: str,
) -> None:
    """Test the Maven CLI command correctly persisting the executable string."""
    parse_res = maven_cli_parser.parse(build_command.split())
    assert parse_res.executable == expected


def test_maven_cli_command_parser_default_value(maven_cli_parser: MavenCLICommandParser) -> None:
    """Test the Maven CLI command parser initialized any option as None if it doesn't exist in the input build command."""
    build_command = "mvn clean package"
    parse_res = maven_cli_parser.parse(build_command.split())

    attr_map = vars(parse_res.options)
    for name, value in attr_map.items():
        if name == "goals":
            assert value == ["clean", "package"]
        else:
            assert not value


@pytest.mark.parametrize(
    ("build_command"),
    [
        pytest.param("", id="An empty build command"),
        pytest.param("mvn", id="No goal or phase"),
        pytest.param(
            "mvn --this-argument-should-never-exist-in-mvn",
            id="Unrecognized optional arguments",
        ),
        pytest.param(
            "mvn --this-argument-should-never-exist-in-mvn some-value",
            id="Unrecognized value option",
        ),
        pytest.param(
            "mmmvvvnnn clean package",
            id="The executable is unacceptable",
        ),
    ],
)
def test_maven_cli_command_parser_invalid_input(
    maven_cli_parser: MavenCLICommandParser,
    build_command: str,
) -> None:
    """Test the Maven CLI command parser on invalid input."""
    with pytest.raises(MavenCLICommandParseError):
        maven_cli_parser.parse(build_command.split())


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(
            {"A": "B"},
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
    ],
)
def test_is_dict_of_str_to_str(value: Any, expected: bool) -> None:
    """Test the is_dict_of_str_to_str type guard."""
    assert is_dict_of_str_to_str(value) == expected


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
    ("command"),
    [
        "mvn clean package",
        "mvn clean package -P profile1,profile2 -T 2C -ntp -Dmaven.skip.test=true -Dboo=foo",
        "mvn -f fit/core-reference/pom.xml verify -Dit.test=RESTITCase -Dinvoker.streamLogs=true"
        + " -Dmodernizer.skip=true -Drat.skip=true -Dcheckstyle.skip=true -Djacoco.skip=true",
        "mvn -s ../.github/maven-settings.xml install -Pexamples,noRun",
    ],
)
def test_to_cmd_goals(maven_cli_parser: MavenCLICommandParser, command: str) -> None:
    """Test the to_cmd_goals method."""
    maven_cli_command = maven_cli_parser.parse(command.split())

    print_command_with_goals = [maven_cli_command.executable]
    print_command_with_goals.extend(maven_cli_command.options.to_cmd_goals())

    maven_cli_command_second = maven_cli_parser.parse(print_command_with_goals)
    assert maven_cli_command == maven_cli_command_second


@pytest.mark.parametrize(
    ("this", "that"),
    [
        ("mvn clean package", "mvn install"),
        ("mvn clean package", "mvn clean package -X"),
        ("mvn clean package", "mvn clean package -P project1,project2"),
        ("mvn clean package", "mvn clean package -Dmaven.skip.test=true"),
        ("mvn clean package", "mvn clean package --settings ./pom.xml"),
        ("mvn clean package", "mvn package clean"),
    ],
)
def test_comparing_maven_cli_options_unequal(
    maven_cli_parser: MavenCLICommandParser,
    this: str,
    that: str,
) -> None:
    """Test comparing two unequal MavenCLIOption objects."""
    this_options = maven_cli_parser.parse(this.split()).options
    that_options = maven_cli_parser.parse(that.split()).options
    assert not this_options == that_options
