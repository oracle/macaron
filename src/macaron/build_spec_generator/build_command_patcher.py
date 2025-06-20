# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the implementation of the build command patching."""

import logging
from collections.abc import Mapping

from macaron.build_spec_generator.gradle_cli_parser import GradleCLICommandParser, GradleOptionPatchValueType
from macaron.build_spec_generator.maven_cli_parser import (
    CommandLineParseError,
    MavenCLICommandParser,
    MavenOptionPatchValueType,
    PatchBuildCommandError,
)

logger: logging.Logger = logging.getLogger(__name__)

MVN_CLI_PARSER = MavenCLICommandParser()
GRADLE_CLI_PARSER = GradleCLICommandParser()


def patch_mvn_cli_command(
    cmd_list: list[str],
    patch_options: Mapping[str, MavenOptionPatchValueType | None],
) -> list[str] | None:
    """Patch a Maven CLI command.

    `patch_options` is a mapping with:

    - **Key**: the long name of a Maven CLI option as a string. For example: ``--define``, ``--settings``.
      For patching goals or plugin phases, use the key `goals` with value being a list of string.
    - **Value**: The value to patch. The type of this value depends on the type of option you want to
      patch.

    The types of patch values:

    - For optional flag (e.g ``-X/--debug``) it is boolean. True to set it and False to unset it.
    - For ``-D/--define`` ONLY, it will be a mapping between the system property name and its value.
    - For options that expects a comma delimited list of string (e.g. ``-P/--activate-profiles``
      and ``-pl/--projects``), a list of string is expected.
    - For other value option (e.g ``-s/--settings``), a string is expected.

    None can be provided to any type of option to remove it from the original build command.

    Parameters
    ----------
    cmd_list : list[str]
        The original Maven command, as list of string. Note that we assume
        that the elements of this list doesn't contain any shell quotes.
        Example: ``["mvn", "clean, "package", "--debug"]``
    patch_options : Mapping[str, PatchOptionType]
        The patch values.

    Returns
    -------
    list[str] | None
        The patched command as a list of strings, or ``None`` if there is an error.
        Errors that can happen in the patching operation can be the original build command is not
        a valid mvn CLI command or the patch mapping is is not in the expected format).
    """
    return _patch_mvn_cli_command(
        cmd_list=cmd_list,
        patch_options=patch_options,
        mvn_cli_parser=MVN_CLI_PARSER,
    )


def _patch_mvn_cli_command(
    cmd_list: list[str],
    patch_options: Mapping[str, MavenOptionPatchValueType | None],
    mvn_cli_parser: MavenCLICommandParser,
) -> list[str] | None:
    """Patch a Maven CLI command by enforcing goals/phases and modifying options.

    This function takes in the mvn cli parser as a parameter. It's designed like this mainly for
    unit testing purposes.
    """
    try:
        mvn_cli_command = mvn_cli_parser.parse(cmd_list)
    except CommandLineParseError as error:
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


def patch_gradle_cli_command(
    cmd_list: list[str],
    patch_options: Mapping[str, GradleOptionPatchValueType | None],
) -> list[str] | None:
    """Patch a Gradle CLI command.

    `patch_options` is a mapping with:

    - **Key**: the long name of an Gradle CLI option as string. For example: ``--continue``, ``--build-cache``.
      For patching tasks, use the key ``tasks``.
    - **Value**: The value to patch for an option referred to by the key. The type of this value
      depends on the type of option you want to patch. Please see the details below.

    The types of patch values:

    - For optional flag (e.g ``-d/--debug``) that doesn't take in a value, it is boolean. True if you want to
      set it, and False if you want to unset it.
    - For ``-D/--system-prop`` and ``-P/--project-prop`` ONLY, it is a a mapping between the property name
      and its value. A value of type None can be provided to "unset" the property.
    - For ``-x/--exclude-task`` option, a list of string is required.
    - For options that have a negated form (e.g. ``--build-cache/--no-build-cache``), the key must be the normal
      long name (``--build-cache``) and the value is of type boolean. True if you want to set ``--build-cache``
      and False if you want to set ``--no-build-cache``.
    - For other option that expects a value (e.g `-c/--setting-file <path/to/settings/file>``), a string is
      expected.

    None can be provided to ANY type of option to forcefully remove it from the original build command.

    Parameters
    ----------
    cmd_list : list[str]
        The original Gradle command, as list of string. Note that we assume
        that the elements of this list doesn't contain any shell quotes.
        Example: ``["gradle", "clean, "build", "--debug"]``
    patch_options : Mapping[str, GradleOptionPatchValueType | None]
        The patch values.

    Returns
    -------
    list[str] | None
        The patched command as a list of strings, or `None` if there is an error.
        Errors that can happen in the patching operation can be: the original build command is not a
        valid Gradle CLI command or the patch mapping is is not in the expected format.
    """
    return _patch_gradle_cli_command(
        cmd_list=cmd_list,
        patch_options=patch_options,
        gradle_cli_parser=GRADLE_CLI_PARSER,
    )


def _patch_gradle_cli_command(
    cmd_list: list[str],
    patch_options: Mapping[str, GradleOptionPatchValueType | None],
    gradle_cli_parser: GradleCLICommandParser,
) -> list[str] | None:
    """Patch a Gradle CLI command by enforcing tasks and/or modifying options.

    This function takes in an object of GradleCLICommandParser as a parameter. It's designed like this mainly for
    unit testing purposes.
    """
    try:
        gradle_cli_command = gradle_cli_parser.parse(cmd_list)
    except CommandLineParseError as error:
        logger.error(
            "Failed to parse the mvn command %s. Error %s.",
            " ".join(cmd_list),
            error,
        )
        return None

    final_result = []
    final_result.append(gradle_cli_command.executable)

    try:
        new_options = gradle_cli_parser.apply_option_patch(
            gradle_cli_command.options,
            patch_options,
        )
    except PatchBuildCommandError as error:
        logger.error(
            "Failed to patch the mvn command %s. Error %s.",
            " ".join(cmd_list),
            error,
        )
        return None

    final_result.extend(new_options.to_cmd_tasks())

    return final_result
