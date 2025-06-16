# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for maven cli parser."""


import pytest

from macaron.build_spec_generator.maven_cli_parser import (
    CommandLineParseError,
    MavenCLICommandParser,
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
        pytest.param(
            "mvn --help",
            {
                "goals": [],
                "help": True,
            },
            id="allow_no_goal_for_help",
        ),
        pytest.param(
            "mvn --version",
            {
                "goals": [],
                "help": False,
                "version": True,
            },
            id="allow_no_goal_for_version",
        ),
        pytest.param(
            "mvn --help --version",
            {
                "goals": [],
                "help": True,
                "version": True,
            },
            id="allow_no_goal_for_version_and_help",
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
            id="unrecognized_optional_argument",
        ),
        pytest.param(
            "mvn --this-argument-should-never-exist-in-mvn some-value",
            id="unrecognized_value_option",
        ),
        pytest.param(
            "mmmvvvnnn clean package",
            id="unrecognized_executable_path",
        ),
        pytest.param(
            "mvn --show-version",
            id="show_version_with_no_goal",
        ),
    ],
)
def test_maven_cli_command_parser_invalid_input(
    maven_cli_parser: MavenCLICommandParser,
    build_command: str,
) -> None:
    """Test the Maven CLI command parser on invalid input."""
    with pytest.raises(CommandLineParseError):
        maven_cli_parser.parse(build_command.split())
