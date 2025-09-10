# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Maven CLI Command parser."""

import argparse
import logging
import os
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, TypeGuard

from macaron.build_spec_generator.cli_command_parser import (
    OptionDef,
    PatchCommandBuildTool,
    is_dict_of_str_to_str_or_none,
    is_list_of_strs,
    patch_mapping,
)
from macaron.build_spec_generator.cli_command_parser.maven_cli_command import MavenCLICommand, MavenCLIOptions
from macaron.errors import CommandLineParseError, PatchBuildCommandError

logger: logging.Logger = logging.getLogger(__name__)


MavenOptionPatchValueType = str | list[str] | bool | dict[str, str | None]


@dataclass
class MavenOptionalFlag(OptionDef[bool]):
    """This option represents an optional flag in Maven CLI command.

    For example: --debug/-X

    A short form for the option is required.
    """

    short_name: str

    # Right now this is used for --help where the default attribute name for it
    # in the returned argparse.Namespace is "--help" which conflicts with the built-in function help().
    dest: str | None = field(default=None)

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[bool]:
        """Return True if the provided patch value is compatible with the internal type of this option."""
        return isinstance(patch, bool)

    def add_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        if self.dest:
            arg_parse.add_argument(
                *(self.short_name, self.long_name),
                action="store_true",
                dest=self.dest,
            )
        else:
            arg_parse.add_argument(
                *(self.short_name, self.long_name),
                action="store_true",
            )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "bool"


@dataclass
class MavenSingleValue(OptionDef[str]):
    """This option represents an option that takes a value in Maven CLI command.

    For example: "--settings ./path/to/pom.xml"

    A short form for the option is required.
    """

    short_name: str

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[str]:
        """Return True if the provided patch value is compatible with the internal type of this option."""
        return isinstance(patch, str)

    def add_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        arg_parse.add_argument(
            *(self.short_name, self.long_name),
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "str"


@dataclass
class MavenCommaDelimList(OptionDef[list[str]]):
    """This option represents an option that takes a comma delimited value in Maven CLI command.

    This option can be defined one time only and the value is stored as a string in argparse.
    However, it's stored internally as list of strings obtained by splitting its original value in argparse
    using comma as the delimiter.

    For example: "-P profile1,profile2,profile3"
    will be stored as ["profile1", "profile2", "profile3"]

    A short form for the option is required.
    """

    short_name: str

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[list[str]]:
        """Return True if the provided patch value is compatible with the internal type of this option."""
        return is_list_of_strs(patch)

    def add_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        arg_parse.add_argument(
            *(self.short_name, self.long_name),
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "list"


@dataclass
class MavenSystemPropeties(OptionDef[dict[str, str | None]]):
    """This option represents the -D/--define option of a Maven CLI command.

    This option can be defined multiple times and the values are appended into a list of string in argparse.
    However, it's stored internally as a dictionary mapping between the system property name to its value.

    For example: ``-Dmaven.skip.test=true -Drat.skip=true``
    will be stored as ``{"maven.skip.test": "true", "rat.skip": "true"}``

    A short form for the option is required.
    """

    short_name: str

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[dict[str, str | None]]:
        """Return True if the provided patch value is compatible with the internal type of this option."""
        return is_dict_of_str_to_str_or_none(patch)

    def add_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        arg_parse.add_argument(
            *(self.short_name, self.long_name),
            action="append",
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "dict[str, str | None]"


@dataclass
class MavenGoalPhase(OptionDef[list[str]]):
    """This option represents the positional goal/plugin-phase option in Maven CLI command.

    argparse.Namespace stores this as a list of string. This is stored internally as a list of string.
    """

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[list[str]]:
        """Return True if the provided patch value is compatible with the internal type of this option."""
        return is_list_of_strs(patch)

    def add_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        # Doesn't require to allow cases like "mvn --help".
        arg_parse.add_argument(
            self.long_name,
            nargs="*",
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "list[str]"


# We intend to support Maven version 3.6.3 - 3.9
MAVEN_OPTION_DEF: list[OptionDef] = [
    MavenOptionalFlag(
        short_name="-am",
        long_name="--also-make",
    ),
    MavenOptionalFlag(
        short_name="-amd",
        long_name="--also-make-dependents",
    ),
    MavenOptionalFlag(
        short_name="-B",
        long_name="--batch-mode",
    ),
    MavenOptionalFlag(
        short_name="-C",
        long_name="--strict-checksums",
    ),
    MavenOptionalFlag(
        short_name="-c",
        long_name="--lax-checksums",
    ),
    MavenOptionalFlag(
        short_name="-cpu",
        long_name="--check-plugin-updates",
    ),
    MavenOptionalFlag(
        short_name="-e",
        long_name="--errors",
    ),
    MavenOptionalFlag(
        short_name="-fae",
        long_name="--fail-at-end",
    ),
    MavenOptionalFlag(
        short_name="-ff",
        long_name="--fail-fast",
    ),
    MavenOptionalFlag(
        short_name="-fn",
        long_name="--fail-never",
    ),
    MavenOptionalFlag(
        short_name="-h",
        long_name="--help",
        dest="help_",
    ),
    MavenOptionalFlag(
        short_name="-llr",
        long_name="--legacy-local-repository",
    ),
    MavenOptionalFlag(
        short_name="-N",
        long_name="--non-recursive",
    ),
    MavenOptionalFlag(
        short_name="-nsu",
        long_name="--no-snapshot-updates",
    ),
    MavenOptionalFlag(
        short_name="-ntp",
        long_name="--no-transfer-progress",
    ),
    MavenOptionalFlag(
        short_name="-npu",
        long_name="--no-plugin-updates",
    ),
    MavenOptionalFlag(
        short_name="-npr",
        long_name="--no-plugin-registry",
    ),
    MavenOptionalFlag(
        short_name="-o",
        long_name="--offline",
    ),
    MavenOptionalFlag(
        short_name="-q",
        long_name="--quiet",
    ),
    MavenOptionalFlag(
        short_name="-U",
        long_name="--update-snapshots",
    ),
    MavenOptionalFlag(
        short_name="-up",
        long_name="--update-plugins",
    ),
    MavenOptionalFlag(
        short_name="-v",
        long_name="--version",
    ),
    MavenOptionalFlag(
        short_name="-V",
        long_name="--show-version",
    ),
    MavenOptionalFlag(
        short_name="-X",
        long_name="--debug",
    ),
    MavenGoalPhase(
        long_name="goals",
    ),
    # TODO: we need to confirm whether one can provide
    # -P or -pl multiple times and the values will be aggregate into a list of string.
    # The current implementation only consider one instance of -P or -pl.
    # Where to begin:
    # https://github.com/apache/maven/blob/maven-3.9.x/maven-embedder/src/main/java/org/apache/maven/cli/CLIManager.java
    # https://github.com/apache/commons-cli/blob/master/src/main/java/org/apache/commons/cli/Parser.java
    MavenSingleValue(
        short_name="-b",
        long_name="--builder",
    ),
    MavenSystemPropeties(
        short_name="-D",
        long_name="--define",
    ),
    MavenSingleValue(
        short_name="-emp",
        long_name="--encrypt-master-password",
    ),
    MavenSingleValue(
        short_name="-ep",
        long_name="--encrypt-password",
    ),
    MavenSingleValue(
        short_name="-f",
        long_name="--file",
    ),
    MavenSingleValue(
        short_name="-gs",
        long_name="--global-settings",
    ),
    MavenSingleValue(
        short_name="-gt",
        long_name="--global-toolchains",
    ),
    MavenSingleValue(
        short_name="-l",
        long_name="--log-file",
    ),
    MavenCommaDelimList(
        short_name="-P",
        long_name="--activate-profiles",
    ),
    MavenCommaDelimList(
        short_name="-pl",
        long_name="--projects",
    ),
    MavenSingleValue(
        short_name="-rf",
        long_name="--resume-from",
    ),
    MavenSingleValue(
        short_name="-s",
        long_name="--settings",
    ),
    MavenSingleValue(
        short_name="-t",
        long_name="--toolchains",
    ),
    MavenSingleValue(
        short_name="-T",
        long_name="--threads",
    ),
]


class MavenCLICommandParser:
    """A Maven CLI Command Parser."""

    ACCEPTABLE_EXECUTABLE = ["mvn", "mvnw"]

    def __init__(self) -> None:
        """Initialize the instance."""
        self.arg_parser = argparse.ArgumentParser(
            description="Parse Maven CLI command",
            prog="mvn",
            add_help=False,
            # https://docs.python.org/3/library/argparse.html#exit-on-error
            # Best effort of parsing the build command. Therefore, we don't want to exit on error.
            exit_on_error=False,
        )

        # A mapping between the long name and its option definition.
        self.option_defs: dict[str, OptionDef] = {}

        for opt_def in MAVEN_OPTION_DEF:
            opt_def.add_to_arg_parser(self.arg_parser)

            self.option_defs[opt_def.long_name] = opt_def

        self.build_tool = PatchCommandBuildTool.MAVEN

    def is_build_tool(self, executable_path: str) -> bool:
        """Return True if ``executable_path`` ends the accepted executable for this build tool.

        Parameters
        ----------
        executable_path: str
            The executable component of a CLI command.

        Returns
        -------
        bool
        """
        return os.path.basename(executable_path) in MavenCLICommandParser.ACCEPTABLE_EXECUTABLE

    def validate_patch(self, patch: Mapping[str, MavenOptionPatchValueType | None]) -> bool:
        """Return True if the patch conforms to the expected format."""
        for patch_name, patch_value in patch.items():
            opt_def = self.option_defs.get(patch_name)
            if not opt_def:
                logger.error("Cannot find any option that matches %s", patch_name)
                return False

            if patch_value is None:
                continue

            if not opt_def.is_valid_patch_option(patch_value):
                logger.error(
                    "The patch value %s of %s is not in the correct type. Expect %s.",
                    patch_value,
                    patch_name,
                    opt_def.get_patch_type_str(),
                )
                return False

        return True

    def parse(self, cmd_list: list[str]) -> "MavenCLICommand":
        """Parse the Maven CLI Command.

        Parameters
        ----------
        cmd_list: list[str]
            The Maven CLI Command as list of strings.

        Returns
        -------
        MavenCLICommand
            The MavenCLICommand instance.

        Raises
        ------
        MavenCLICommandParseError
            If an error happens when parsing the Maven CLI Command.
        """
        if not cmd_list:
            raise CommandLineParseError("The provided cmd list is empty.")

        exe_path = cmd_list[0]
        options = cmd_list[1:]

        if os.path.basename(exe_path) not in MavenCLICommandParser.ACCEPTABLE_EXECUTABLE:
            raise CommandLineParseError(f"{exe_path} is not an acceptable mvn executable path.")

        # TODO: because our parser is not completed for all cases, should we be more relaxed and use
        # parse_unknown_options?
        try:
            parsed_opts = self.arg_parser.parse_args(options)
        except argparse.ArgumentError as error:
            raise CommandLineParseError(f"Failed to parse command {' '.join(options)}.") from error
        # Even though we have set `exit_on_error`, argparse still exists unexpectedly in some
        # cases. This has been confirmed to be a bug in the argparse library implementation.
        # https://github.com/python/cpython/issues/121018.
        # This is fixed in Python3.12, but not Python3.11
        except SystemExit as sys_exit_err:
            raise CommandLineParseError(f"Failed to parse the Maven CLI Options {' '.join(options)}.") from sys_exit_err

        # Handle cases where goal or plugin phase is not provided.
        if not parsed_opts.goals:
            # Allow cases such as:
            #   mvn --help
            #   mvn --version
            # Note that we don't allow mvn -V or mvn --show-version as this command will
            #   fail for mvn.
            if not parsed_opts.help_ and not parsed_opts.version:
                raise CommandLineParseError(f"No goal detected for {' '.join(options)}.")

        maven_cli_options = MavenCLIOptions.from_parsed_arg(parsed_opts)

        return MavenCLICommand(
            executable=exe_path,
            options=maven_cli_options,
        )

    def _patch_properties_mapping(
        self,
        original_props: dict[str, str],
        option_long_name: str,
        patch_value: MavenOptionPatchValueType,
    ) -> dict[str, str]:
        define_opt_def = self.option_defs.get(option_long_name)
        if not define_opt_def or not isinstance(define_opt_def, MavenSystemPropeties):
            raise PatchBuildCommandError(f"{option_long_name} from the patch is not a --define option.")

        if not define_opt_def.is_valid_patch_option(patch_value):
            raise PatchBuildCommandError(f"Critical, incorrect runtime type for patch --define, value: {patch_value}.")

        return patch_mapping(
            original=original_props,
            patch=patch_value,
        )

    def apply_patch(
        self,
        cli_command: MavenCLICommand,
        options_patch: Mapping[str, MavenOptionPatchValueType | None],
    ) -> MavenCLICommand:
        """Patch the options of a Gradle CLI command, while persisting the executable path.

        `options_patch` is a mapping with:

        - **Key**: the long name of a Maven CLI option as a string. For example: ``--define``, ``--settings``.
          For patching goals or plugin phases, use the key `goals` with the value being a list of strings.

        - **Value**: The value to patch. The type of this value depends on the type of option to be patched.

        The types of patch values:

        - For optional flag (e.g ``-X/--debug``) it is boolean. True to set it and False to unset it.

        - For ``-D/--define`` ONLY, it will be a mapping between the system property name and its value.

        - For options that expects a comma delimited list of string (e.g. ``-P/--activate-profiles``
          and ``-pl/--projects``), a list of string is expected.

        - For other value option (e.g ``-s/--settings``), a string is expected.

        None can be provided to any type of option to remove it from the original build command.

        Parameters
        ----------
        cli_command : MavenCLICommand
            The original Maven command, as a ``MavenCLICommand`` object from ``MavenCLICommand.parse(...)``
        patch_options : Mapping[str, MavenOptionPatchValueType | None]
            The patch values.

        Returns
        -------
        MavenCLICommand
            The patched command as a new ``MavenCLICommand`` object.

        Raises
        ------
        PatchBuildCommandError
            If an error happens during the patching process.
        """
        return MavenCLICommand(
            executable=cli_command.executable,
            options=self.apply_option_patch(
                cli_command.options,
                patch=options_patch,
            ),
        )

    def apply_option_patch(
        self,
        maven_cli_options: MavenCLIOptions,
        patch: Mapping[str, MavenOptionPatchValueType | None],
    ) -> MavenCLIOptions:
        """Patch the Maven CLI Options and return a new copy.

        Parameters
        ----------
        maven_cli_options: MavenCLIOptions
            The Maven CLI Options to patch.
        patch: Mapping[str, PatchValueType | None]
            A mapping between the name of the attribute in MavenCLIOptions and its patch value.
            The value can be None to disable an option.

        Returns
        -------
        MavenCLIOptions
            The new patched maven cli options.

        Raises
        ------
        PatchBuildCommandError
            If an error happens during the patching process.
        """
        if not self.validate_patch(patch):
            raise PatchBuildCommandError("The patch is invalid.")

        # Copy the Maven CLI Options for patching
        new_maven_cli_options = deepcopy(maven_cli_options)

        for option_long_name, patch_value in patch.items():
            if option_long_name == "--help":
                attr_name = "_help"
            else:
                # Get the attribute name of MavenCLIOption object.
                # They all follow the same rule of removing the prefix --
                # from option long name and replace all "-" with "_"
                attr_name = option_long_name.removeprefix("--").replace("-", "_")

            # Ensure that setting any option to None in the patch
            # will remove it from the build command.
            if patch_value is None:
                setattr(new_maven_cli_options, attr_name, patch_value)
                continue

            # Only for "-D/--define" we patch it differently.
            if option_long_name == "--define":
                new_maven_cli_options.define = self._patch_properties_mapping(
                    original_props=new_maven_cli_options.define or {},
                    option_long_name=option_long_name,
                    patch_value=patch_value,
                )
                continue

            setattr(new_maven_cli_options, attr_name, patch_value)

        return new_maven_cli_options
