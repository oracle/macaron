# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the implementation of the build command patching."""

import logging
from collections.abc import Mapping

from macaron.build_spec_generator.maven_cli_parser import (
    MavenCLICommandParseError,
    MvnCLICommandParser,
    MvnOptionPatchValueType,
    PatchBuildCommandError,
)

logger: logging.Logger = logging.getLogger(__name__)

MVN_CLI_PARSER = MvnCLICommandParser()


def patch_mvn_cli_command(
    cmd_list: list[str],
    patch_options: Mapping[str, MvnOptionPatchValueType],
) -> list[str] | None:
    """Patch a Maven CLI command.

    Parameters
    ----------
    cmd_list : list[str]
        The original Maven command, as list of string. Note that we assume
        that the elements of this list doesn't contain any shell quotes.
        Example: ["mvn", "clean, "package", "--debug"]
    patch_options : Mapping[str, PatchOptionType]
        The patch information as a mapping with:
        - Key: str the long name of an mvn CLI option. For example: --define, --settings. For patching
        goals or plugin phases, use the key `goals` with value being a list of string.
        - Value: The value to patch. The type of this value depends on the type of option you want to
        patch. For optional flag (e.g `-X/--debug`) it is boolean. For `-D/--define` ONLY, it
        will be a mapping between the system property name and its value. For options that expects
        a comma delimited list of string (e.g. `-P/--activate-profiles` and `-pl/--projects`), a
        list of string is expected. For other value option (e.g "-s/--settings"), a string is expected.
        None can be provided to any type of option to remove it from the original build command.

    Returns
    -------
    list[str] | None
        The patched command as a list of strings, or `None` if there is an error.
        Errors that can happen in the patching operation can be
        - The original build command is not a valid mvn CLI command.
        - The patch mapping is is not in the expected format).
    """
    return _patch_mvn_cli_command(
        cmd_list=cmd_list,
        patch_options=patch_options,
        mvn_cli_parser=MVN_CLI_PARSER,
    )


def _patch_mvn_cli_command(
    cmd_list: list[str],
    patch_options: Mapping[str, MvnOptionPatchValueType],
    mvn_cli_parser: MvnCLICommandParser,
) -> list[str] | None:
    """Patch a Maven CLI command by enforcing goals/phases and modifying options.

    This function takes in the mvn cli parser as a parameter. And it's designed like this mainly for
    unit testing purposes.
    """
    try:
        mvn_cli_command = mvn_cli_parser.parse(cmd_list)
    except MavenCLICommandParseError as error:
        logger.error(
            "Failed to parse the mvn command %s. Error %s.",
            " ".join(cmd_list),
            error,
        )
        return None

    final_result = []
    final_result.append(mvn_cli_command.executable)

    try:
        new_options = mvn_cli_parser.apply_option_patch(
            mvn_cli_command.options,
            patch_options,
        )
    except PatchBuildCommandError as error:
        logger.error(
            "Failed to patch the mvn command %s. Error %s.",
            " ".join(cmd_list),
            error,
        )
        return None

    final_result.extend(new_options.to_cmd_goals())

    return final_result
