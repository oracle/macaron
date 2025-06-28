# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the test for the build command patcher."""

from collections.abc import Mapping

import pytest

from macaron.build_spec_generator.build_command_patcher import (
    CLICommand,
    CLICommandParser,
    PatchValueType,
    _patch_commands,
)
from macaron.build_spec_generator.cli_command_parser import PatchCommandBuildTool
from macaron.build_spec_generator.cli_command_parser.gradle_cli_parser import (
    GradleCLICommandParser,
    GradleOptionPatchValueType,
)
from macaron.build_spec_generator.cli_command_parser.maven_cli_parser import (
    MavenCLICommandParser,
    MavenOptionPatchValueType,
)
from macaron.build_spec_generator.cli_command_parser.unparsed_cli_command import UnparsedCLICommand


@pytest.mark.parametrize(
    ("original", "patch_options", "expected"),
    [
        pytest.param(
            "mvn install -X",
            {},
            "mvn install -X",
            id="no_patch_value",
        ),
        pytest.param(
            "mvn install -X",
            {"goals": ["clean", "package"]},
            "mvn clean package -X",
            id="patch_goals_should_persist_order",
        ),
        pytest.param(
            "mvn install",
            {
                "--no-transfer-progress": True,
            },
            "mvn install -ntp",
            id="patching_an_optional_flag",
        ),
        pytest.param(
            "mvn install",
            {
                "--threads": "2C",
            },
            "mvn install -T 2C",
            id="patching_single_value_option",
        ),
        pytest.param(
            "mvn install",
            {
                "--activate-profiles": ["profile1", "profile2"],
            },
            "mvn install -P profile1,profile2",
            id="patching_comma_delimt_list_value_option",
        ),
        pytest.param(
            "mvn install",
            {
                "--define": {
                    "maven.skip.test": "true",
                    "rat.skip": "true",
                },
            },
            "mvn install -Dmaven.skip.test=true -Drat.skip=true",
            id="patching_system_properties",
        ),
        # The patch for -D/--define merge with the original the system properties. The patch will always takes precedence.
        pytest.param(
            "mvn install -Dmaven.skip.test=false -Dboo=foo",
            {
                "goals": ["clean", "package"],
                "--define": {
                    "maven.skip.test": "true",
                    "rat.skip": "true",
                },
            },
            "mvn clean package -Dmaven.skip.test=true -Drat.skip=true -Dboo=foo",
            id="patching_system_properties_merging",
        ),
        pytest.param(
            "mvn install -Dmaven.skip.test=false -Dboo=foo",
            {
                "goals": ["clean", "package"],
                "--define": {
                    "maven.skip.test": None,
                    "rat.skip": "true",
                },
            },
            "mvn clean package -Drat.skip=true -Dboo=foo",
            id="patching_system_properties_disable",
        ),
        pytest.param(
            "mvn install -T 2C -ntp -Dmaven.skip.test=true",
            {
                "--threads": None,
                "--no-transfer-progress": None,
                "--define": None,
            },
            "mvn install",
            id="removing_any_option_using_None",
        ),
    ],
)
def test_patch_mvn_cli_command(
    maven_cli_parser: MavenCLICommandParser,
    original: str,
    patch_options: Mapping[str, MavenOptionPatchValueType | None],
    expected: str,
) -> None:
    """Test the patch maven cli command on valid input."""
    patch_cmds = _patch_commands(
        cmds_sequence=[original.split()],
        cli_parsers=[maven_cli_parser],
        patches={PatchCommandBuildTool.MAVEN: patch_options},
    )
    assert patch_cmds
    assert len(patch_cmds) == 1

    patch_mvn_cli_command = maven_cli_parser.parse(patch_cmds.pop().to_cmds())
    expected_mvn_cli_command = maven_cli_parser.parse(expected.split())

    assert patch_mvn_cli_command == expected_mvn_cli_command


@pytest.mark.parametrize(
    ("invalid_patch"),
    [
        pytest.param(
            {
                "--this-option-should-never-exist": True,
            },
            id="unrecognised_option_name",
        ),
        pytest.param(
            {
                "--define": True,
            },
            id="incorrect_define_option_type",
        ),
        pytest.param(
            {
                "--debug": "some_value",
            },
            id="incorrect_debug_option_type",
        ),
        pytest.param(
            {
                "--settings": False,
            },
            id="incorrect_settings_option_type",
        ),
        pytest.param(
            {
                "--activate-profiles": False,
            },
            id="incorrect_activate_profiles_option_type",
        ),
    ],
)
def test_patch_mvn_cli_command_error(
    maven_cli_parser: MavenCLICommandParser,
    invalid_patch: dict[str, MavenOptionPatchValueType | None],
) -> None:
    """Test patch mvn cli command patching with invalid patch."""
    cmd_list = "mvn -s ../.github/maven-settings.xml install -Pexamples,noRun".split()

    assert (
        _patch_commands(
            cmds_sequence=[cmd_list],
            cli_parsers=[maven_cli_parser],
            patches={
                PatchCommandBuildTool.MAVEN: invalid_patch,
            },
        )
        is None
    )


@pytest.mark.parametrize(
    ("original", "patch_options", "expected"),
    [
        pytest.param(
            "gradle --build-cache clean build",
            {},
            "gradle --build-cache clean build",
            id="no_patch_value",
        ),
        pytest.param(
            "gradle --build-cache clean build",
            {"--build-cache": False},
            "gradle --no-build-cache clean build",
            id="test_patching_negateable_option",
        ),
        pytest.param(
            "gradle clean",
            {"tasks": ["clean", "build"]},
            "gradle clean build",
            id="patch_tasks_should_persist_order",
        ),
        pytest.param(
            "gradle clean build",
            {"--debug": True},
            "gradle --debug clean build",
            id="patching_an_optional_flag",
        ),
        pytest.param(
            "gradle clean build",
            {
                "--debug": True,
                "--continue": True,
            },
            "gradle --debug --continue clean build",
            id="patching_an_optional_flag",
        ),
        pytest.param(
            "gradle clean build",
            {"--console": "plain"},
            "gradle --console plain clean build",
            id="patching_a_single_value_option",
        ),
        pytest.param(
            "gradle clean build -Pboo=foo",
            {
                "--system-prop": {
                    "org.gradle.caching": "true",
                },
                "--project-prop": {
                    "bar": "",
                    "boo": "another_foo",
                },
            },
            "gradle clean build -Dorg.gradle.caching=true -Pbar -Pboo=another_foo",
            id="patching_properties",
        ),
        pytest.param(
            "gradle clean build -Pboo=foo",
            {
                "--project-prop": {
                    "boo": None,
                }
            },
            "gradle clean build",
            id="removing_a_property_using_none",
        ),
        pytest.param(
            "gradle clean build",
            {"--exclude-task": ["boo", "test"]},
            "gradle clean build -x boo -x test",
            id="excluding_tasks",
        ),
        pytest.param(
            "gradle clean build --debug -x test -Dorg.gradle.caching=true -Pboo=foo --console=plain --no-build-cache",
            {
                "--exclude-task": None,
                "--debug": None,
                "--system-prop": None,
                "--project-prop": None,
                "--console": None,
                "--build-cache": None,
            },
            "gradle clean build",
            id="removing_any_option_using_none",
        ),
    ],
)
def test_patch_gradle_cli_command(
    gradle_cli_parser: GradleCLICommandParser,
    original: str,
    patch_options: dict[str, GradleOptionPatchValueType | None],
    expected: str,
) -> None:
    """Test the patch gradle cli command on valid input."""
    patch_cmds = _patch_commands(
        cmds_sequence=[original.split()],
        cli_parsers=[gradle_cli_parser],
        patches={PatchCommandBuildTool.GRADLE: patch_options},
    )
    assert patch_cmds
    assert len(patch_cmds) == 1

    patch_gradle_cli_command = gradle_cli_parser.parse(patch_cmds.pop().to_cmds())
    expected_gradle_cli_command = gradle_cli_parser.parse(expected.split())

    assert patch_gradle_cli_command == expected_gradle_cli_command


@pytest.mark.parametrize(
    ("invalid_patch"),
    [
        pytest.param(
            {
                "--this-option-should-never-exist": True,
            },
            id="unrecognised_option_name",
        ),
        pytest.param(
            {
                "--system-prop": True,
            },
            id="incorrect_system_prop_option_type",
        ),
        pytest.param(
            {
                "--project-prop": True,
            },
            id="incorrect_project_prop_option_type",
        ),
        pytest.param(
            {
                "--debug": "some_value",
            },
            id="incorrect_debug_option_type",
        ),
        pytest.param(
            {
                "--init-script": False,
            },
            id="incorrect_init_script_option_type",
        ),
        pytest.param(
            {
                "--exclude-task": False,
            },
            id="incorrect_exclude_task_option_type",
        ),
        pytest.param(
            {
                "tasks": False,
            },
            id="incorrect_tasks_type",
        ),
        pytest.param(
            {
                "--no-build-cache": True,
            },
            id="cannot_use_negated_form_option_as_key_in_patch",
        ),
    ],
)
def test_patch_gradle_cli_command_error(
    gradle_cli_parser: GradleCLICommandParser,
    invalid_patch: dict[str, GradleOptionPatchValueType | None],
) -> None:
    """Test patch mvn cli command patching with invalid patch."""
    cmd_list = "gradle clean build --no-build-cache --debug --console plain -Dorg.gradle.parallel=true".split()
    assert (
        _patch_commands(
            cmds_sequence=[cmd_list],
            cli_parsers=[gradle_cli_parser],
            patches={
                PatchCommandBuildTool.GRADLE: invalid_patch,
            },
        )
        is None
    )


@pytest.mark.parametrize(
    ("cmds_sequence", "patches", "expected"),
    [
        pytest.param(
            [
                "mvn clean package".split(),
                "gradle clean build".split(),
            ],
            {
                PatchCommandBuildTool.MAVEN: {
                    "--debug": True,
                },
                PatchCommandBuildTool.GRADLE: {
                    "--debug": True,
                },
            },
            [
                "mvn clean package --debug".split(),
                "gradle clean build --debug".split(),
            ],
            id="apply_multiple_types_of_patches",
        ),
        pytest.param(
            [
                "mvn clean package".split(),
                "gradle clean build".split(),
            ],
            {
                PatchCommandBuildTool.MAVEN: {
                    "--debug": True,
                },
            },
            [
                "mvn clean package --debug".split(),
                "gradle clean build".split(),
            ],
            id="apply_one_type_of_patch_to_multiple_commands",
        ),
        pytest.param(
            [
                "mvn clean package".split(),
                "gradle clean build".split(),
            ],
            {},
            [
                "mvn clean package".split(),
                "gradle clean build".split(),
            ],
            id="apply_no_patch_to_multiple_build_commands",
        ),
        pytest.param(
            [
                "make setup".split(),
                "mvn clean package".split(),
                "gradle clean build".split(),
                "make clean".split(),
            ],
            {
                PatchCommandBuildTool.MAVEN: {
                    "--debug": True,
                },
                PatchCommandBuildTool.GRADLE: {
                    "--debug": True,
                },
            },
            [
                "make setup".split(),
                "mvn clean package --debug".split(),
                "gradle clean build --debug".split(),
                "make clean".split(),
            ],
            id="command_that_we_cannot_parse_stay_the_same",
        ),
    ],
)
def test_patching_multiple_commands(
    maven_cli_parser: MavenCLICommandParser,
    gradle_cli_parser: GradleCLICommandParser,
    cmds_sequence: list[list[str]],
    patches: Mapping[
        PatchCommandBuildTool,
        Mapping[str, PatchValueType | None],
    ],
    expected: list[list[str]],
) -> None:
    """Test patching multiple commands."""
    patch_cli_commands = _patch_commands(
        cmds_sequence=cmds_sequence,
        cli_parsers=[maven_cli_parser, gradle_cli_parser],
        patches=patches,
    )

    assert patch_cli_commands

    expected_cli_commands: list[CLICommand] = []
    cli_parsers: list[CLICommandParser] = [maven_cli_parser, gradle_cli_parser]
    for cmd in expected:
        effective_cli_parser = None
        for cli_parser in cli_parsers:
            if cli_parser.is_build_tool(cmd[0]):
                effective_cli_parser = cli_parser
                break

        if effective_cli_parser:
            expected_cli_commands.append(cli_parser.parse(cmd))
        else:
            expected_cli_commands.append(
                UnparsedCLICommand(
                    original_cmds=cmd,
                )
            )

    assert patch_cli_commands == expected_cli_commands


@pytest.mark.parametrize(
    ("cmds_sequence", "patches"),
    [
        pytest.param(
            [
                "mvn --this-is-not-a-mvn-option".split(),
                "gradle clean build".split(),
            ],
            {
                PatchCommandBuildTool.MAVEN: {
                    "--debug": True,
                },
                PatchCommandBuildTool.GRADLE: {
                    "--debug": True,
                },
            },
            id="incorrect_mvn_command",
        ),
        pytest.param(
            [
                "mvn clean package".split(),
                "gradle clean build --not-a-gradle-command".split(),
            ],
            {
                PatchCommandBuildTool.MAVEN: {
                    "--debug": True,
                },
                PatchCommandBuildTool.GRADLE: {
                    "--debug": True,
                },
            },
            id="incorrect_gradle_command",
        ),
        pytest.param(
            [
                "mvn clean package".split(),
                "gradle clean build".split(),
            ],
            {
                PatchCommandBuildTool.MAVEN: {
                    "--not-a-valid-option": True,
                },
            },
            id="incorrrect_patch_option_long_name",
        ),
        pytest.param(
            [
                "mvn clean package".split(),
                "gradle clean build".split(),
            ],
            {
                PatchCommandBuildTool.MAVEN: {
                    # --debug expects a boolean or a None value.
                    "--debug": 10,
                },
            },
            id="incorrrect_patch_value",
        ),
    ],
)
def test_patching_multiple_commands_error(
    maven_cli_parser: MavenCLICommandParser,
    gradle_cli_parser: GradleCLICommandParser,
    cmds_sequence: list[list[str]],
    patches: Mapping[
        PatchCommandBuildTool,
        Mapping[str, PatchValueType | None],
    ],
) -> None:
    """Test error cases for patching multiple commands."""
    assert (
        _patch_commands(
            cmds_sequence=cmds_sequence,
            cli_parsers=[maven_cli_parser, gradle_cli_parser],
            patches=patches,
        )
        is None
    )
