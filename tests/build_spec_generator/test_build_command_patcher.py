# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the test for the build command patcher."""

import pytest

from macaron.build_spec_generator.build_command_patcher import _patch_mvn_cli_command
from macaron.build_spec_generator.maven_cli_parser import MavenCLICommandParser, MavenOptionPatchValueType


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
    patch_options: dict[str, MavenOptionPatchValueType],
    expected: str,
) -> None:
    """Test the patch maven cli command on valid input."""
    patch_cmds = _patch_mvn_cli_command(
        cmd_list=original.split(),
        patch_options=patch_options,
        mvn_cli_parser=maven_cli_parser,
    )
    assert patch_cmds

    patch_mvn_cli_command = maven_cli_parser.parse(patch_cmds)

    expected_mvn_cli_command = maven_cli_parser.parse(expected.split())

    assert patch_mvn_cli_command == expected_mvn_cli_command


@pytest.mark.parametrize(
    ("invalid_patch"),
    [
        pytest.param(
            {
                "--this-option-should-never-exist": True,
            },
            id="Patching an unrecognised mvn option name.",
        ),
        pytest.param(
            {
                "--define": True,
            },
            id="The patching value is not the exected type. --define expects patch None | dict[str, str]",
        ),
        pytest.param(
            {
                "--debug": "some_value",
            },
            id="The patching value is not the exected type. --debug expects patch None | bool",
        ),
        pytest.param(
            {
                "--settings": False,
            },
            id="The patching value is not the exected type. --settings expects patch None | str",
        ),
        pytest.param(
            {
                "--activate-profiles": False,
            },
            id="The patching value is not the exected type. --activate-profiles expects patch None | list[str]",
        ),
    ],
)
def test_patch_mvn_cli_command_error(
    maven_cli_parser: MavenCLICommandParser,
    invalid_patch: dict[str, MavenOptionPatchValueType],
) -> None:
    """Test patch mvn cli command patching with invalid patch."""
    assert not _patch_mvn_cli_command(
        cmd_list="mvn -s ../.github/maven-settings.xml install -Pexamples,noRun".split(),
        patch_options=invalid_patch,
        mvn_cli_parser=maven_cli_parser,
    )
