# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the implementation of the build command patching."""

import logging
from collections.abc import Mapping

from macaron.build_spec_generator.maven_cli_parser import (
    MavenCLICommandParseError,
    MvnCLICommand,
    MvnOptionPatchValueType,
)

logger: logging.Logger = logging.getLogger(__name__)


def patch_maven_cli_command(
    cmd_list: list[str],
    force_goals_phases: list[str],
    patch_options: Mapping[str, MvnOptionPatchValueType],
) -> list[str] | None:
    """Patch a Maven CLI command by enforcing goals/phases and modifying options.

    Parameters
    ----------
    cmd_list : list[str]
        The original Maven command, as list of string. Note that we assume
        that the elements of this list doesn't contain any shell quotes.
    force_goals_phases : list[str]
        A list of Maven goals or plugin phases to enforce. The order in which each goal/phase
        appear in the list will be persisted in the final build command.
    patch_options : Mapping[str, PatchOptionType]
        The patch information as a mapping with:
        - Key: str the long name of an option, without the "--" prefix and any "-" replaced by
        "_". For example -D/--define becomes "define", -ntp/--no-transfer-progress becomes "no_transfer_progress".
        - Value: The value to apply. The value depends on the type of option you want to
        patch. For optional flag (e.g `--debug`) it is boolean. For `-D/--define` only, it
        will be a mapping between the system property name and its value. For other
        value option (e.g "-s/--settings"), a string is expected. A None can be provided
        to remove the option from the final build command.

    Returns
    -------
    list of str or None
        The patched command as a list of strings, or `None` if there is an error (e.g. the original build command is invalid).
    """
    try:
        mvn_cli_command = MvnCLICommand.from_list_of_string(
            cmd_as_list=cmd_list,
            accepted_mvn_executable=["mvn", "mvnw"],
        )
    except MavenCLICommandParseError as error:
        logger.error(
            "Failed to parse the mvn command %s. Error %s.",
            " ".join(cmd_list),
            error,
        )
        return None

    final_result = []
    final_result.append(mvn_cli_command.executable)

    mvn_cli_command.options.apply_patch(
        patch=patch_options,
    )

    if force_goals_phases:
        final_result.extend(force_goals_phases)
        final_result.extend(mvn_cli_command.options.to_cmd_no_goals())
    else:
        final_result.extend(mvn_cli_command.options.to_cmd_goals())

    return final_result
