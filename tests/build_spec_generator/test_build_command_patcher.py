# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the test for the build command patcher."""

from collections.abc import Mapping

import pytest

from macaron.build_spec_generator.build_command_patcher import (
    PatchValueType,
    _patch_command,
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
    patch_cmd = _patch_command(
        cmd=original.split(),
        cli_parsers=[maven_cli_parser],
        patches={PatchCommandBuildTool.MAVEN: patch_options},
    )
    assert patch_cmd

    patch_mvn_cli_command = maven_cli_parser.parse(patch_cmd.to_cmds())
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
    original_cmd = "mvn -s ../.github/maven-settings.xml install -Pexamples,noRun".split()

    assert (
        _patch_command(
            cmd=original_cmd,
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
    patch_cmd = _patch_command(
        cmd=original.split(),
        cli_parsers=[gradle_cli_parser],
        patches={PatchCommandBuildTool.GRADLE: patch_options},
    )
    assert patch_cmd

    patch_gradle_cli_command = gradle_cli_parser.parse(patch_cmd.to_cmds())
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
    original_cmd = "gradle clean build --no-build-cache --debug --console plain -Dorg.gradle.parallel=true".split()
    assert (
        _patch_command(
            cmd=original_cmd,
            cli_parsers=[gradle_cli_parser],
            patches={
                PatchCommandBuildTool.GRADLE: invalid_patch,
            },
        )
        is None
    )


@pytest.mark.parametrize(
    ("original", "patch_options", "expected"),
    [
        pytest.param(
            "make setup",
            {
                "--threads": None,
                "--no-transfer-progress": None,
                "--define": None,
            },
            "make setup",
            id="make_command",
        ),
        pytest.param(
            "./configure",
            {
                "--threads": None,
                "--no-transfer-progress": None,
                "--define": None,
            },
            "./configure",
            id="configure_command",
        ),
    ],
)
def test_patch_arbitrary_command(
    maven_cli_parser: MavenCLICommandParser,
    original: str,
    patch_options: Mapping[str, MavenOptionPatchValueType | None],
    expected: str,
) -> None:
    """Test the patch function for arbitrary commands."""
    patched_cmd = _patch_command(
        cmd=original.split(),
        cli_parsers=[maven_cli_parser],
        patches={PatchCommandBuildTool.MAVEN: patch_options},
    )
    assert patched_cmd
    assert patched_cmd.to_cmds() == expected.split()


@pytest.mark.parametrize(
    ("cmd", "patches"),
    [
        pytest.param(
            "mvn --this-is-not-a-mvn-option".split(),
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
            "gradle clean build --not-a-gradle-command".split(),
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
            "mvn clean package".split(),
            {
                PatchCommandBuildTool.MAVEN: {
                    "--not-a-valid-option": True,
                },
            },
            id="incorrect_patch_option_long_name",
        ),
        pytest.param(
            "mvn clean package".split(),
            {
                PatchCommandBuildTool.MAVEN: {
                    # --debug expects a boolean or a None value.
                    "--debug": 10,
                },
            },
            id="incorrect_patch_value",
        ),
    ],
)
def test_multiple_patches_error(
    maven_cli_parser: MavenCLICommandParser,
    gradle_cli_parser: GradleCLICommandParser,
    cmd: list[str],
    patches: Mapping[
        PatchCommandBuildTool,
        Mapping[str, PatchValueType | None],
    ],
) -> None:
    """Test error cases for multiple patches and parsers."""
    assert (
        _patch_command(
            cmd=cmd,
            cli_parsers=[maven_cli_parser, gradle_cli_parser],
            patches=patches,
        )
        is None
    )


@pytest.mark.parametrize(
    ("original_cmd"),
    [
        pytest.param(
            [],
            id="empty command",
        ),
    ],
)
def test_empty_command(maven_cli_parser: MavenCLICommandParser, original_cmd: list[str]) -> None:
    """Test the patch command for an empty command."""
    patch_cmd = _patch_command(
        cmd=original_cmd,
        cli_parsers=[maven_cli_parser],
        patches={PatchCommandBuildTool.MAVEN: {}},
    )
    assert patch_cmd is None
