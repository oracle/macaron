# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Maven CLI Command parser."""

import argparse
import os
from collections.abc import Mapping
from typing import Any, TypeGuard

from macaron.errors import MavenCLICommandParseError, PatchBuildCommandError

MvnOptionPatchValueType = str | list[str] | bool | dict[str, str] | None


def get_mvn_argument_parser() -> argparse.ArgumentParser:
    """Return the argparse.ArgumentParser instances used to parse Maven CLI command.

    Returns
    -------
    argparse.ArgumentParser
        The argparse.ArgumentParser instance with all argument initialized.
    """
    arg_parser = argparse.ArgumentParser(
        description="Parse Maven CLI command",
        prog="mvn",
        add_help=False,
        # https://docs.python.org/3/library/argparse.html#exit-on-error
        # Best effort of parsing the build command. Therefore, we don't want to exit on error.
        exit_on_error=False,
    )
    arg_parser.add_argument(
        *("-am", "--also-make"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-amd", "--also-make-dependents"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-B", "--batch-mode"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-b", "--builder"),
    )

    arg_parser.add_argument(
        *("-C", "--strict-checksums"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-c", "--lax-checksums"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-D", "--define"),
        action="append",
    )

    arg_parser.add_argument(
        *("-e", "--errors"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-emp", "--encrypt-master-password"),
    )

    arg_parser.add_argument(
        *("-ep", "--encrypt-password"),
    )

    arg_parser.add_argument(
        *("-f", "--file"),
    )

    arg_parser.add_argument(
        *("-fae", "--fail-at-end"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-ff", "--fail-fast"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-fn", "--fail-never"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-gs", "--global-settings"),
    )

    arg_parser.add_argument(
        *("-gt", "--global-toolchains"),
    )

    arg_parser.add_argument(
        *("-h", "--help"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-l", "--log-file"),
    )

    arg_parser.add_argument(
        *("-N", "--non-recursive"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-nsu", "--no-snapshot-updates"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-ntp", "--no-transfer-progress"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-o", "--offline"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-P", "--activate-profiles"),
    )

    arg_parser.add_argument(
        *("-pl", "--projects"),
    )

    arg_parser.add_argument(
        *("-q", "--quiet"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-rf", "--resume-from"),
    )

    arg_parser.add_argument(
        *("-s", "--settings"),
    )

    arg_parser.add_argument(
        *("-t", "--toolchains"),
    )

    arg_parser.add_argument(
        *("-T", "--threads"),
    )

    arg_parser.add_argument(
        *("-U", "--update-snapshots"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-v", "--version"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-V", "--show-version"),
        action="store_true",
    )

    arg_parser.add_argument(
        *("-X", "--debug"),
        action="store_true",
    )

    arg_parser.add_argument(
        "goals",
        nargs="+",
    )

    return arg_parser


class MvnCLIOptions:
    """The class that stores the values of options parsed from a Maven CLI Command."""

    mvn_arg_parser = get_mvn_argument_parser()

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
            MvnCLIOptions.parse_system_properties(parsed_arg.define) if parsed_arg.define else None
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
        self.help_: bool | None = parsed_arg.help
        self.log_file: str | None = parsed_arg.log_file
        self.non_recursive: bool | None = parsed_arg.non_recursive
        self.no_snapshot_updates: bool | None = parsed_arg.no_snapshot_updates
        self.no_transfer_progress: bool | None = parsed_arg.no_transfer_progress
        self.offline: bool | None = parsed_arg.offline
        self.activate_profiles: list[str] | None = (
            MvnCLIOptions.parse_comma_sep_list(parsed_arg.activate_profiles) if parsed_arg.activate_profiles else None
        )
        self.projects: list[str] | None = (
            MvnCLIOptions.parse_comma_sep_list(parsed_arg.projects) if parsed_arg.projects else None
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
        if not isinstance(value, MvnCLIOptions):
            return False

        return sorted(vars(self)) == sorted(vars(value))

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
        >>> MvnCLIOptions.parse_system_properties(["boo=true", "foo=1"])
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
        >>> MvnCLIOptions.parse_comma_sep_list("examples,release")
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
            result.append(f"-b {self.builder}")

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
            result.append(f"-emp {self.encrypt_master_password}")

        if self.encrypt_password:
            result.append(f"-ep {self.encrypt_password}")

        if self.file:
            result.append(f"-f {self.file}")

        if self.fail_at_end:
            result.append("-fae")

        if self.fail_fast:
            result.append("-ff")

        if self.fail_never:
            result.append("-fn")

        if self.global_settings:
            result.append(f"-gs {self.global_settings}")

        if self.global_toolchains:
            result.append(f"-gt {self.global_toolchains}")

        if self.help_:
            result.append("-h")

        if self.log_file:
            result.append(f"-l {self.log_file}")

        if self.non_recursive:
            result.append("-N")

        if self.no_snapshot_updates:
            result.append("-U")

        if self.no_transfer_progress:
            result.append("-ntp")

        if self.offline:
            result.append("-o")

        if self.activate_profiles:
            result.append(f"-P {','.join(self.activate_profiles)}")

        if self.projects:
            result.append(f"-pl {','.join(self.projects)}")

        if self.quiet:
            result.append("-q")

        if self.resume_from:
            result.append(f"-rf {self.resume_from}")

        if self.settings:
            result.append(f"-s {self.settings}")

        if self.toolchains:
            result.append(f"-t {self.toolchains}")

        if self.threads:
            result.append(f"-T {self.threads}")

        if self.update_snapshots:
            result.append("-U")

        if self.version:
            result.append("-v")

        if self.show_version:
            result.append("-V")

        if self.debug:
            result.append("-X")

        return result

    @staticmethod
    def is_system_prop_dict(values: Any) -> TypeGuard[dict[str, str]]:
        """Type guard for system property dictionary."""
        if not isinstance(values, dict):
            return False

        for key, value in values.items():
            if not isinstance(key, str):
                return False
            if not isinstance(value, str):
                return False

        return True

    @staticmethod
    def from_list_of_string(option_strs: list[str]) -> "MvnCLIOptions":
        """Parse the options part of the Maven CLI command.

        Parameters
        ----------
        list[str]
            The options to parse

        Returns
        -------
        MvnCLIOptions
            The MvnCLIOptions that capture the informatino of the provided options.

        Raises
        ------
        MavenCLICommandParseError
            If an error happens during parsing.
        """
        try:
            parsed_args = MvnCLIOptions.mvn_arg_parser.parse_args(option_strs)
        except argparse.ArgumentError as error:
            raise MavenCLICommandParseError(
                f"Failed to parse the Maven CLI Options {' '.join(option_strs)}."
            ) from error
        # Even though we have set `exit_on_error`, argparse still exists unexpectedly in some
        # cases. This has been confirmed to be a bug in argparse implementation.
        # https://github.com/python/cpython/issues/121018.
        # This is fixed in Python3.12, but not Python3.11
        except SystemExit as sys_exit_err:
            raise MavenCLICommandParseError(
                f"Failed to parse the Maven CLI Options {' '.join(option_strs)}."
            ) from sys_exit_err

        return MvnCLIOptions(parsed_args)

    def apply_patch(
        self,
        patch: Mapping[str, MvnOptionPatchValueType],
    ) -> None:
        """Apply a patch to the option values contained in an MvnCLIOptions instance.

        This function will mutate the attributes of the MvnCLIOptions instance.

        Parameters
        ----------
        patch: Mapping[str, PatchOptionType]
            A mapping between the name of the attribute in MvnCLIOptions and its patch value
        """
        for attr_name, attr_value in patch.items():
            # Ensure that setting any option to None in the patch
            # will remove it from the build command.
            if attr_value is None:
                setattr(self, attr_name, attr_value)
                continue

            if attr_name == "define":
                if not MvnCLIOptions.is_system_prop_dict(attr_value):
                    raise PatchBuildCommandError(
                        f"The patch value for --define flag {attr_value} is not of type dict[str, str]"
                    )

                self.define = patch_mapping(
                    original=self.define or {},
                    patch=attr_value,
                )

                continue

            setattr(self, attr_name, attr_value)


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


class MvnCLICommand:
    """The class that stores the values of a Maven CLI Command."""

    def __init__(
        self,
        executable: str,
        options: MvnCLIOptions,
    ) -> None:
        """Initialize the instance.

        Parameters
        ----------
        executeable : str
            The executable part of the build command (e.g. mvnw, mvn or ./path/to/mvnw).

        options: MvnCLIOptions
            The MvnCLIOptions object created from parsing the options part of the build command.
        """
        self.executable = executable
        self.options = options

    def __eq__(self, value: Any) -> bool:
        if not isinstance(value, MvnCLICommand):
            return False

        return self.executable == value.executable and self.options == value.options

    @staticmethod
    def from_list_of_string(
        cmd_as_list: list[str],
        accepted_mvn_executable: list[str],
    ) -> "MvnCLICommand":
        """Parse a Maven CLI command.

        Parameters
        ----------
        list[str]
            The Maven CLI command, as list of strings.

        Returns
        -------
        MvnCLICommand
            The MvnCLICommand that capture the information of the provided Maven CLI command.

        Raises
        ------
        MavenCLICommandParseError
            If an error happens during parsing.
        """
        if not cmd_as_list:
            raise MavenCLICommandParseError("The provided cmd list is empty.")

        exe_path = cmd_as_list[0]
        options = cmd_as_list[1:]

        if os.path.basename(exe_path) not in accepted_mvn_executable:
            raise MavenCLICommandParseError(f"{exe_path} is not an acceptable mvn executable path.")

        try:
            mvn_cli_options = MvnCLIOptions.from_list_of_string(options)
        except MavenCLICommandParseError as error:
            raise MavenCLICommandParseError(f"Failed to parse options of {' '.join(cmd_as_list)}.") from error

        return MvnCLICommand(
            executable=exe_path,
            options=mvn_cli_options,
        )
