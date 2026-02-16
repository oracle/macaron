# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
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

CLI_COMMAND_PATCHES: dict[
    PatchCommandBuildTool,
    Mapping[str, PatchValueType | None],
] = {
    PatchCommandBuildTool.MAVEN: {
        "goals": ["clean", "package"],
        "--batch-mode": False,
        "--quiet": False,
        "--no-transfer-progress": False,
        # Example pkg:maven/io.liftwizard/liftwizard-servlet-logging-mdc@1.0.1
        # https://github.com/liftwizard/liftwizard/blob/
        # 4ea841ffc9335b22a28a7a19f9156e8ba5820027/.github/workflows/build-and-test.yml#L23
        "--threads": None,
        # For cases such as
        # pkg:maven/org.apache.isis.valuetypes/isis-valuetypes-prism-resources@2.0.0-M7
        "--version": False,
        "--define": {
            # pkg:maven/org.owasp/dependency-check-utils@7.3.2
            # To remove "-Dgpg.passphrase=$MACARON_UNKNOWN"
            "gpg.passphrase": None,
            "skipTests": "true",
            "maven.site.skip": "true",
            "rat.skip": "true",
            "maven.javadoc.skip": "true",
        },
    },
    PatchCommandBuildTool.GRADLE: {
        "tasks": ["clean", "assemble"],
        "--console": "plain",
        "--exclude-task": ["test"],
        "--project-prop": {
            "skip.signing": "",
            "skipSigning": "",
            "gnupg.skip": "",
        },
    },
}


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
    for cmd in cmds_sequence:
        # Checking if the command is a valid non-empty list.
        if not cmd:
            continue
        effective_cli_parser = None
        for cli_parser in cli_parsers:
            if cli_parser.is_build_tool(cmd[0]):
                effective_cli_parser = cli_parser
                break

        if not effective_cli_parser:
            result.append(UnparsedCLICommand(original_cmds=cmd))
            continue

        try:
            cli_command = effective_cli_parser.parse(cmd)
        except CommandLineParseError as error:
            logger.error(
                "Failed to patch the cli command %s. Error %s.",
                " ".join(cmd),
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
                patch_options=patch,
            )
        except PatchBuildCommandError as error:
            logger.error(
                "Failed to patch the build command %s. Error %s.",
                " ".join(cmd),
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

    - If the command is not a build command, or it's a tool we do not support, it will be left intact.

    - If the command is a build command we support, it will be patched, if a patch value is provided in ``patches``.
      If no patch value is provided for a build command, it will be left intact.

    `patches` is a mapping with:

    - **Key**: an instance of the ``BuildTool`` enum

    - **Value**: the patch value provided to ``CLICommandParser.apply_patch``. For more information on the patch value
      see the concrete implementations of the ``CLICommandParser.apply_patch`` method.
      For example: :class:`macaron.cli_command_parser.maven_cli_parser.MavenCLICommandParser.apply_patch`,
      :class:`macaron.cli_command_parser.gradle_cli_parser.GradleCLICommandParser.apply_patch`.

    This means that all commands that match a BuildTool will be applied by the same patch value.

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
