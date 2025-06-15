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
from macaron.errors import MavenCLICommandParseError, PatchBuildCommandError

logger: logging.Logger = logging.getLogger(__name__)


MavenOptionPatchValueType = str | list[str] | bool | dict[str, str] | None


def is_list_of_strs(value: Any) -> TypeGuard[list[str]]:
    """Type guard for a list of strings."""
    return isinstance(value, list) and all(isinstance(ele, str) for ele in value)


def is_dict_of_str_to_str(value: Any) -> TypeGuard[list[str]]:
    """Type guard for a dictionary with keys are string and values are strings."""
    return isinstance(value, dict) and all(isinstance(key, str) and isinstance(val, str) for key, val in value.items())


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
        arg_parse.add_argument(
            self.long_name,
            nargs="+",
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "list[str]"


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


class MavenCLIOptions:
    """The class that stores the values of options parsed from a Maven CLI Command."""

    def __init__(
        self,
        parsed_arg: argparse.Namespace,
    ) -> None:
        """Initialize the instance.

        Parameters
        ----------
        parsed_arg : argparse.Namespace
            The argparse.Namespace object obtained from parsing the CLI Command.
        """
        self.also_make: bool | None = parsed_arg.also_make
        self.also_make_dependents: bool | None = parsed_arg.also_make_dependents
        self.batch_mode: bool | None = parsed_arg.batch_mode
        self.builder: str | None = parsed_arg.builder
        self.strict_checksums: bool | None = parsed_arg.strict_checksums
        self.lax_checksums: bool | None = parsed_arg.lax_checksums
        self.define: dict[str, str] | None = (
            MavenCLIOptions.parse_system_properties(parsed_arg.define) if parsed_arg.define else None
        )
        self.errors: bool | None = parsed_arg.errors
        self.encrypt_master_password: str | None = parsed_arg.encrypt_master_password
        self.encrypt_password: str | None = parsed_arg.encrypt_password
        self.file: str | None = parsed_arg.file
        self.fail_at_end: bool | None = parsed_arg.fail_at_end
        self.fail_fast: bool | None = parsed_arg.fail_fast
        self.fail_never: bool | None = parsed_arg.fail_never
        self.global_settings: str | None = parsed_arg.global_settings
        self.global_toolchains: str | None = parsed_arg.global_toolchains
        self.help: bool | None = parsed_arg.help
        self.log_file: str | None = parsed_arg.log_file
        self.non_recursive: bool | None = parsed_arg.non_recursive
        self.no_snapshot_updates: bool | None = parsed_arg.no_snapshot_updates
        self.no_transfer_progress: bool | None = parsed_arg.no_transfer_progress
        self.offline: bool | None = parsed_arg.offline
        self.activate_profiles: list[str] | None = (
            MavenCLIOptions.parse_comma_sep_list(parsed_arg.activate_profiles) if parsed_arg.activate_profiles else None
        )
        self.projects: list[str] | None = (
            MavenCLIOptions.parse_comma_sep_list(parsed_arg.projects) if parsed_arg.projects else None
        )
        self.quiet: bool | None = parsed_arg.quiet
        self.resume_from: str | None = parsed_arg.resume_from
        self.settings: str | None = parsed_arg.settings
        self.toolchains: str | None = parsed_arg.toolchains
        self.threads: str | None = parsed_arg.threads
        self.update_snapshots: bool | None = parsed_arg.update_snapshots
        self.version: bool | None = parsed_arg.version
        self.show_version: bool | None = parsed_arg.show_version
        self.debug: bool | None = parsed_arg.debug
        self.goals: list[str] = parsed_arg.goals

    def __eq__(self, value: Any) -> bool:
        if not isinstance(value, MavenCLIOptions):
            return False

        return vars(self) == vars(value)

    @staticmethod
    def parse_system_properties(props: list[str]) -> dict[str, str]:
        """Return a dictionary that maps between a system propertie and its value.

        Parameters
        ----------
        props: list[str]
            The list of values provided to -D/--define in the cli command.
            For example: if the command is `mvn -Dboo=foo -Dbar=far clean install`
            then props will be ["boo=foo", "bar=far"]

        Returns
        -------
        dict[str, str]:
            The system properties dictionary.

        Examples
        --------
        >>> MavenCLIOptions.parse_system_properties(["boo=true", "foo=1"])
        {'boo': 'true', 'foo': '1'}
        """
        system_props = {}
        for ele in props:
            prop_name, _, prop_val = ele.partition("=")
            # Allow the subsequent definition override the previous one.
            # This follows the way Maven is resolving system property.
            # For example:
            #   mvn help:evaluate -Da=foo -Da=bar -Dexpression=a -q -DforceStdout
            # => result for `a` is bar
            system_props[prop_name] = prop_val

        return system_props

    @staticmethod
    def parse_comma_sep_list(input_val: str) -> list[str]:
        """Split a comma delimited string and return a list of string elements.

        Parameters
        ----------
        input_val: str
            The comma delimited string.

        Returns
        -------
        list[str]
            The list of string elements.

        Examples
        --------
        >>> MavenCLIOptions.parse_comma_sep_list("examples,release")
        ['examples', 'release']
        """
        return input_val.split(",")

    def to_cmd_goals(self) -> list[str]:
        """Return the goals/phases and options as a list of string.

        Only enabled options are returned.

        Returns
        -------
        list[str]
            The goals/phases and options.
        """
        result = self.to_cmd_no_goals()
        for goal in self.goals:
            result.append(goal)

        return result

    def to_cmd_no_goals(self) -> list[str]:
        """Return the options only as a list of string.

        Only enabled options are returned.

        Returns
        -------
        list[str]
            The enabled options.
        """
        result = []

        if self.also_make:
            result.append("-am")

        if self.also_make_dependents:
            result.append("-amd")

        if self.batch_mode:
            result.append("-B")

        if self.builder:
            result.extend(f"-b {self.builder}".split())

        if self.strict_checksums:
            result.append("-C")

        if self.lax_checksums:
            result.append("-c")

        if self.define:
            for key, value in self.define.items():
                result.append(f"-D{key}={value}")

        if self.errors:
            result.append("-e")

        if self.encrypt_master_password:
            result.extend(f"-emp {self.encrypt_master_password}".split())

        if self.encrypt_password:
            result.extend(f"-ep {self.encrypt_password}".split())

        if self.file:
            result.extend(f"-f {self.file}".split())

        if self.fail_at_end:
            result.append("-fae")

        if self.fail_fast:
            result.append("-ff")

        if self.fail_never:
            result.append("-fn")

        if self.global_settings:
            result.extend(f"-gs {self.global_settings}".split())

        if self.global_toolchains:
            result.extend(f"-gt {self.global_toolchains}".split())

        if self.help:
            result.append("-h")

        if self.log_file:
            result.extend(f"-l {self.log_file}".split())

        if self.non_recursive:
            result.append("-N")

        if self.no_snapshot_updates:
            result.append("-U")

        if self.no_transfer_progress:
            result.append("-ntp")

        if self.offline:
            result.append("-o")

        if self.activate_profiles:
            result.extend(f"-P {','.join(self.activate_profiles)}".split())

        if self.projects:
            result.extend(f"-pl {','.join(self.projects)}".split())

        if self.quiet:
            result.append("-q")

        if self.resume_from:
            result.extend(f"-rf {self.resume_from}".split())

        if self.settings:
            result.extend(f"-s {self.settings}".split())

        if self.toolchains:
            result.extend(f"-t {self.toolchains}".split())

        if self.threads:
            result.extend(f"-T {self.threads}".split())

        if self.update_snapshots:
            result.append("-U")

        if self.version:
            result.append("-v")

        if self.show_version:
            result.append("-V")

        if self.debug:
            result.append("-X")

        return result


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


class MavenCLICommand:
    """The class that stores the values of a Maven CLI Command."""

    def __init__(
        self,
        executable: str,
        options: MavenCLIOptions,
    ) -> None:
        """Initialize the instance.

        Parameters
        ----------
        executeable : str
            The executable part of the build command (e.g. mvnw, mvn or ./path/to/mvnw).

        options: MavenCLIOptions
            The MavenCLIOptions object created from parsing the options part of the build command.
        """
        self.executable = executable
        self.options = options

    def __eq__(self, value: Any) -> bool:
        if not isinstance(value, MavenCLICommand):
            return False

        return self.executable == value.executable and self.options == value.options


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

        try:
            parsed_opts = self.arg_parser.parse_args(options)
        except argparse.ArgumentError as error:
            raise MavenCLICommandParseError(f"Failed to parse the Maven CLI Options {' '.join(options)}.") from error
        # Even though we have set `exit_on_error`, argparse still exists unexpectedly in some
        # cases. This has been confirmed to be a bug in the argparse library implementation.
        # https://github.com/python/cpython/issues/121018.
        # This is fixed in Python3.12, but not Python3.11
        except SystemExit as sys_exit_err:
            raise MavenCLICommandParseError(
                f"Failed to parse the Maven CLI Options {' '.join(options)}."
            ) from sys_exit_err

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
