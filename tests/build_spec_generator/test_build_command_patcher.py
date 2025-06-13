# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the test for the build command patcher."""

import pytest

from macaron.build_spec_generator.build_command_patcher import patch_maven_cli_command
from macaron.build_spec_generator.maven_cli_parser import MvnCLICommand, MvnOptionPatchValueType


@pytest.mark.parametrize(
    ("original", "force_goals_phases", "patch_options", "expected"),
    [
        pytest.param(
            "mvn install -X",
            [],
            {},
            "mvn install -X",
            id="No force goal/phase is provided, should use the original",
        ),
        pytest.param(
            "mvn install -X",
            ["clean", "package"],
            {},
            "mvn clean package -X",
            id="The force goals/phases you persist their order in the force_goals_phases input list",
        ),
        pytest.param(
            "mvn install",
            ["clean", "package"],
            {
                "no_transfer_progress": True,
            },
            "mvn clean package -ntp",
            id="Enabling a flag by setting it to True in the patch",
        ),
        pytest.param(
            "mvn install",
            ["clean", "package"],
            {
                "threads": "2C",
                "activate_profiles": "profile1,profile2",
            },
            "mvn clean package -T 2C -P profile1,profile2",
            id="Setting a value option flag by setting its value as string in the patch",
        ),
        pytest.param(
            "mvn install",
            ["clean", "package"],
            {
                "define": {
                    "maven.skip.test": "true",
                    "rat.skip": "true",
                },
            },
            "mvn clean package -Dmaven.skip.test=true -Drat.skip=true",
            id="Defining system properties using a dictionary",
        ),
        pytest.param(
            "mvn install -Dmaven.skip.test=false -Dboo=foo",
            ["clean", "package"],
            {
                "define": {
                    "maven.skip.test": "true",
                    "rat.skip": "true",
                },
            },
            "mvn clean package -Dmaven.skip.test=false -Drat.skip=true -Dboo=foo",
            id="The patch for -D/--define can merge the system properties, with the patch takes precedence.",
        ),
        pytest.param(
            "mvn install -T 2C -ntp -Dmaven.skip.test=true",
            ["clean", "package"],
            {
                "threads": None,
                "no_transfer_progress": None,
                "define": None,
            },
            "mvn clean package",
            id="Remove any type of option by setting its value to None in the patch",
        ),
    ],
)
def test_patch_maven_cli_command(
    original: str,
    force_goals_phases: list[str],
    patch_options: dict[str, MvnOptionPatchValueType],
    expected: str,
) -> None:
    """Test the patch maven cli command on valid input."""
    patch_cmds = patch_maven_cli_command(
        cmd_list=original.split(),
        force_goals_phases=force_goals_phases,
        patch_options=patch_options,
    )
    assert patch_cmds
    accept_exes = ["mvn", "mvnw"]

    patch_command = MvnCLICommand.from_list_of_string(
        cmd_as_list=patch_cmds,
        accepted_mvn_executable=accept_exes,
    )

    expected_command = MvnCLICommand.from_list_of_string(
        cmd_as_list=expected.split(),
        accepted_mvn_executable=accept_exes,
    )

    assert patch_command == expected_command
