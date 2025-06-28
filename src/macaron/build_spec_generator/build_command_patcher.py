# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the implementation of the build command patching."""

import logging
from collections.abc import Mapping, Sequence

from macaron.build_spec_generator.cli_command_parser import CLICommand, CLICommandParser, PatchCommandBuildTool
from macaron.build_spec_generator.cli_command_parser.gradle_cli_parser import (
    GradleCLICommandParser,
    GradleOptionPatchValueType,
)
from macaron.build_spec_generator.cli_command_parser.maven_cli_parser import (
    CommandLineParseError,
    MavenCLICommandParser,
    MavenOptionPatchValueType,
    PatchBuildCommandError,
)
from macaron.build_spec_generator.cli_command_parser.unparsed_cli_command import UnparsedCLICommand

logger: logging.Logger = logging.getLogger(__name__)

MVN_CLI_PARSER = MavenCLICommandParser()
GRADLE_CLI_PARSER = GradleCLICommandParser()

PatchValueType = GradleOptionPatchValueType | MavenOptionPatchValueType


def _patch_commands(
    cmds_sequence: Sequence[list[str]],
    cli_parsers: Sequence[CLICommandParser],
    patches: Mapping[
        PatchCommandBuildTool,
        Mapping[str, PatchValueType | None],
    ],
) -> list[CLICommand] | None:
    """Patch the sequence of build commands, using the provided CLICommandParser instances.

    For each command in `cmds_sequence`, it will be checked against all CLICommandParser instances until there is
    one that can parse it, then a patch from ``patches`` is applied for this command if provided.

    If a command doesn't have any corresponding ``CLICommandParser`` instance it will be parsed as UnparsedCLICommand,
    which just holds the original command as a list of string, without any changes.
    """
    result: list[CLICommand] = []
    for cmds in cmds_sequence:
        effective_cli_parser = None
        for cli_parser in cli_parsers:
            if cli_parser.is_build_tool(cmds[0]):
                effective_cli_parser = cli_parser
                break

        if not effective_cli_parser:
            result.append(UnparsedCLICommand(original_cmds=cmds))
            continue

        try:
            cli_command = effective_cli_parser.parse(cmds)
        except CommandLineParseError as error:
            logger.error(
                "Failed to parse the mvn command %s. Error %s.",
                " ".join(cmds),
                error,
            )
            return None

        patch = patches.get(effective_cli_parser.build_tool, None)
        if not patch:
            result.append(cli_command)
            continue

        try:
            new_cli_command = effective_cli_parser.apply_patch(
                cli_command=cli_command,
                options_patch=patch,
            )
        except PatchBuildCommandError as error:
            logger.error(
                "Failed to patch the mvn command %s. Error %s.",
                " ".join(cmds),
                error,
            )
            return None

        result.append(new_cli_command)

    return result


def patch_commands(
    cmds_sequence: Sequence[list[str]],
    patches: Mapping[
        PatchCommandBuildTool,
        Mapping[str, PatchValueType | None],
    ],
) -> list[list[str]] | None:
    """Patch a sequence of CLI commands.

    For each command in this command sequence:

    - If the command is not a build command or the build tool is not supported by us, it will be leave intact.

    - If the command is a build command supported by us, it will be patch if a patch value is provided to ``patches``.
      If no patch value is provided for a build command, it will be leave intact.

    `patches` is a mapping with:

    - **Key**: an instance of the ``BuildTool`` enum

    - **Value**: the patch value provided to ``CLICommandParser.apply_patch``. For more information on the patch value
      see the concrete implementations of the ``CLICommandParser.apply_patch`` method.
      For example: :class:`macaron.cli_command_parser.maven_cli_parser.MavenCLICommandParser.apply_patch`,
      :class:`macaron.cli_command_parser.gradle_cli_parser.GradleCLICommandParser.apply_patch`.

    This means that all commands that matches a BuildTool will be apply by the same patch value.

    Returns
    -------
    list[list[str]] | None
        The patched command sequence or None if there is an error. The errors that can happen if any command
        which we support is invalid in ``cmds_sequence``, or the patch value is valid.
    """
    result = []
    patch_cli_commands = _patch_commands(
        cmds_sequence=cmds_sequence,
        cli_parsers=[MVN_CLI_PARSER, GRADLE_CLI_PARSER],
        patches=patches,
    )

    if patch_cli_commands is None:
        return None

    for patch_cmd in patch_cli_commands:
        result.append(patch_cmd.to_cmds())

    return result
