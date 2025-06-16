# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Maven CLI Command parser."""

import argparse
import logging
import os
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, TypeGuard

from macaron.build_spec_generator.base_cli_option import Option
from macaron.build_spec_generator.maven_cli_command import MavenCLICommand, MavenCLIOptions
from macaron.errors import MavenCLICommandParseError, PatchBuildCommandError

logger: logging.Logger = logging.getLogger(__name__)


MavenOptionPatchValueType = str | list[str] | bool | dict[str, str] | None


def is_list_of_strs(value: Any) -> TypeGuard[list[str]]:
    """Type guard for a list of strings."""
    return isinstance(value, list) and all(isinstance(ele, str) for ele in value)


def is_dict_of_str_to_str(value: Any) -> TypeGuard[list[str]]:
    """Type guard for a dictionary with keys are string and values are strings."""
    return isinstance(value, dict) and all(isinstance(key, str) and isinstance(val, str) for key, val in value.items())


def patch_mapping(
    original: Mapping[str, str],
    patch: Mapping[str, str | None],
) -> dict[str, str]:
    """Patch a mapping.

    A key with value in patch set to None will be removed from the original.

    Parameters
    ----------
    original: Mapping[str, str]
        The original mapping.
    patch: Mapping[str, str | None]
        The patch.

    Returns
    -------
    dict[str, str]:
        The new dictionary after applying the patch.
    """
    patch_result = dict(original)

    for name, value in patch.items():
        if value is None:
            patch_result.pop(name, None)
        else:
            patch_result[name] = value

    return patch_result


@dataclass
class MavenOptionalFlag(Option[bool]):
    """This option represents an optional flag in Maven CLI command.

    For example: --debug/-X

    A short form for the option is rquired.
    """

    short_name: str

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[bool]:
        """Return True if the provide patch value is compatible with the internal type of this option."""
        if patch is None or isinstance(patch, bool):
            return True

        return False

    def add_itself_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        arg_parse.add_argument(
            *(self.short_name, self.long_name),
            action="store_true",
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "bool"


@dataclass
class MavenSingleValue(Option[str]):
    """This option represents an option that takes a value in Maven CLI command.

    For example: "--settings ./path/to/pom.xml"

    A short form for the option is required.
    """

    short_name: str

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[str]:
        """Return True if the provide patch value is compatible with the internal type of this option."""
        if patch is None or isinstance(patch, str):
            return True

        return False

    def add_itself_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        arg_parse.add_argument(
            *(self.short_name, self.long_name),
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "str"


@dataclass
class MavenCommaDelimList(Option[list[str]]):
    """This option represents an option that takes a comma delimited value in Maven CLI command.

    This option can be defined one time only and the value is stored as a string in argparse.
    However, it's stored internally as list of strings obtained by spliting its original value in argparse
    using comma as the delimiter.

    For example: "-P profile1,profile2,profile3"
    will be store as ["profile1", "profile2", "profile3"]

    A short form for the option is required.
    """

    short_name: str

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[list[str]]:
        """Return True if the provide patch value is compatible with the internal type of this option."""
        if patch is None or is_list_of_strs(patch):
            return True

        return False

    def add_itself_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        arg_parse.add_argument(
            *(self.short_name, self.long_name),
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "list[str]"


@dataclass
class MavenSystemPropeties(Option[dict[str, str]]):
    """This option represents the -D/--define option of a Maven CLI command.

    This option can be defined multiple times and the values are appended into a list of string in argparse.
    However, it's stored internally as a dictionary mapping between the system property name to its value.

    For example: ``-Dmaven.skip.test=true -Drat.skip=true``
    will be stored as ``{"maven.skip.test": "true", "rat.skip": "true"}``

    A short form for the option is required.
    """

    short_name: str

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[dict[str, str]]:
        """Return True if the provide patch value is compatible with the internal type of this option."""
        if patch is None or is_dict_of_str_to_str(patch):
            return True

        return False

    def add_itself_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        arg_parse.add_argument(
            *(self.short_name, self.long_name),
            action="append",
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "dict[str, str]"


@dataclass
class MavenGoalPhase(Option[list[str]]):
    """This option represents the positional goal/plugin-phase option in Maven CLI command.

    argparse.Namespace stores this as a list of string. This is stored internally as a list of string.
    """

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[list[str]]:
        """Return True if the provide patch value is compatible with the internal type of this option."""
        if patch is None or is_list_of_strs(patch):
            return True

        return False

    def add_itself_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        # Doesn't require to allow cases like "mvn --help".
        arg_parse.add_argument(
            self.long_name,
            nargs="*",
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "list[str]"


# TODO: we need to confirm whether one can provide
# -P or -pl multiple times and the values will be aggregate into a list of string
# The current implementation only consider one instance of -P or -pl.
# Where to begin:
# - https://github.com/apache/maven/blob/maven-3.9.x/maven-embedder/src/main/java/org/apache/maven/cli/CLIManager.java
# - https://github.com/apache/commons-cli/blob/master/src/main/java/org/apache/commons/cli/Parser.java
# We intend to support Maven after version 3.6.3
MAVEN_OPTION_DEF: list[Option] = [
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
    MavenSingleValue(
        short_name="-b",
        long_name="--builder",
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
    MavenSystemPropeties(
        short_name="-D",
        long_name="--define",
    ),
    MavenOptionalFlag(
        short_name="-e",
        long_name="--errors",
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
    MavenSingleValue(
        short_name="-gs",
        long_name="--global-settings",
    ),
    MavenSingleValue(
        short_name="-gt",
        long_name="--global-toolchains",
    ),
    MavenOptionalFlag(
        short_name="-h",
        long_name="--help",
    ),
    MavenSingleValue(
        short_name="-l",
        long_name="--log-file",
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
    MavenCommaDelimList(
        short_name="-P",
        long_name="--activate-profiles",
    ),
    MavenCommaDelimList(
        short_name="-pl",
        long_name="--projects",
    ),
    MavenOptionalFlag(
        short_name="-q",
        long_name="--quiet",
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

        # A mapping between the long name to its option definition.
        self.option_defs: dict[str, Option] = {}

        for opt_def in MAVEN_OPTION_DEF:
            opt_def.add_itself_to_arg_parser(self.arg_parser)

            self.option_defs[opt_def.long_name] = opt_def

    def validate_patch(self, patch: Mapping[str, MavenOptionPatchValueType]) -> bool:
        """Return True if the patch conforms to the expected format."""
        for patch_name, patch_value in patch.items():
            opt_def = self.option_defs.get(patch_name)
            if not opt_def:
                logger.error("Cannot find any option that matches %s", patch_name)
                return False

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
            raise MavenCLICommandParseError("The provided cmd list is empty.")

        exe_path = cmd_list[0]
        options = cmd_list[1:]

        if os.path.basename(exe_path) not in MavenCLICommandParser.ACCEPTABLE_EXECUTABLE:
            raise MavenCLICommandParseError(f"{exe_path} is not an acceptable mvn executable path.")

        # TODO: because our parser is not completed for all cases, should we be more relaxed and use
        # parse_unknown_options?
        try:
            parsed_opts = self.arg_parser.parse_args(options)
        except argparse.ArgumentError as error:
            raise MavenCLICommandParseError(f"Critical: Unexpected {' '.join(options)}.") from error
        # Even though we have set `exit_on_error`, argparse still exists unexpectedly in some
        # cases. This has been confirmed to be a bug in the argparse library implementation.
        # https://github.com/python/cpython/issues/121018.
        # This is fixed in Python3.12, but not Python3.11
        except SystemExit as sys_exit_err:
            raise MavenCLICommandParseError(
                f"Failed to parse the Maven CLI Options {' '.join(options)}."
            ) from sys_exit_err

        # Handle cases where goal or plugin phase is not provided.
        if not parsed_opts.goals:
            # Allow cases such as:
            #   mvn --help
            #   mvn --version
            # Note that we don't allow mvn -V or mvn --show-version as this command will
            #   failed for mvn
            if not parsed_opts.help and not parsed_opts.version:
                raise MavenCLICommandParseError(f"No goal detected for {' '.join(options)}.")

        maven_cli_options = MavenCLIOptions(parsed_opts)

        return MavenCLICommand(
            executable=exe_path,
            options=maven_cli_options,
        )

    def apply_option_patch(
        self,
        maven_cli_options: MavenCLIOptions,
        patch: Mapping[str, MavenOptionPatchValueType],
    ) -> MavenCLIOptions:
        """Patch the Maven CLI Options and return a new copy.

        Parameters
        ----------
        maven_cli_options: MavenCLIOptions
            The Maven CLI Options to patch.
        patch: Mapping[str, PatchOptionType]
            A mapping between the name of the attribute in MavenCLIOptions and its patch value

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
            # Get the attribute name of MavenCLIOption object.
            # They all follow the same rule of removing the prefix --
            # from option long name and replace all "-" with "_"
            attr_name = option_long_name.removeprefix("--").replace("-", "_")

            # Ensure that setting any option to None in the patch
            # will remove it from the build command.
            if patch_value is None:
                setattr(new_maven_cli_options, attr_name, patch_value)
                continue

            # Only for "-D/--define" we patch it differently than other options.
            if option_long_name == "--define":
                define_opt_def = self.option_defs.get(option_long_name)
                if not define_opt_def or not define_opt_def.is_valid_patch_option(patch_value):
                    # Shouldn't happen
                    raise PatchBuildCommandError(
                        f"Critical, incorrect runtime type for patch --define, value: {patch_value}."
                    )
                new_maven_cli_options.define = patch_mapping(
                    original=new_maven_cli_options.define or {},
                    patch=patch_value,
                )
                continue

            setattr(new_maven_cli_options, attr_name, patch_value)

        return new_maven_cli_options
