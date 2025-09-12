# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for maven cli parser."""


import pytest

from macaron.build_spec_generator.cli_command_parser.maven_cli_parser import (
    CommandLineParseError,
    MavenCLICommandParser,
)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        pytest.param(
            "mvn clean package",
            {"goals": ["clean", "package"]},
            id="goal_only_no_option",
        ),
        # https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html#Build_Lifecycle_Basics
        pytest.param(
            "mvn clean dependency:copy-dependencies package",
            {"goals": ["clean", "dependency:copy-dependencies", "package"]},
            id="goal_and_phase_mix",
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
            id="test_combination_options",
        ),
        pytest.param(
            "mvn clean package -Dmaven.skip.test=true -Dmaven.skip.test=false",
            {
                "goals": ["clean", "package"],
                "define": {"maven.skip.test": "false"},
            },
            id="multiple_definition_of_the_same_property_override_each_other",
        ),
        pytest.param(
            "mvn clean package -Dmaven.skip.test",
            {
                "goals": ["clean", "package"],
                "define": {"maven.skip.test": "true"},
            },
            id="test_default_value_if_no_value_is_provided_for_a_property",
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
                "help_": True,
            },
            id="allow_no_goal_for_help",
        ),
        pytest.param(
            "mvn --version",
            {
                "goals": [],
                "help_": False,
                "version": True,
            },
            id="allow_no_goal_for_version",
        ),
        pytest.param(
            "mvn --help --version",
            {
                "goals": [],
                "help_": True,
                "version": True,
            },
            id="allow_no_goal_for_version_and_help",
        ),
        pytest.param(
            "mvn",
            {
                "goals": [],
                "help_": False,
                "version": False,
            },
            id="No goal or phase",
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

    all_attrs = vars(parsed_res.options).keys()

    for attribute in all_attrs:
        if attribute in expected:
            assert getattr(parsed_res.options, attribute) == expected[attribute]
        else:
            # Making sure that we are not enabling flags that are not part of the
            # build command.
            # We don't compare it to None because some options if not set, argparse
            # will assign a different Falsy value depending on the option type.
            # For example
            #   - If `--help` is not provide, its value will be False
            #   - If `--settings` is not provided, its value will be None.
            assert not getattr(parsed_res.options, attribute)


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


@pytest.mark.parametrize(
    ("build_command"),
    [
        pytest.param("", id="An empty command"),
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
    ],
)
def test_maven_cli_command_parser_invalid_input(
    maven_cli_parser: MavenCLICommandParser,
    build_command: str,
) -> None:
    """Test the Maven CLI command parser on invalid input."""
    with pytest.raises(CommandLineParseError):
        maven_cli_parser.parse(build_command.split())
