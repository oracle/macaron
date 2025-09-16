# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Gradle CLI Command parser."""

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
from macaron.build_spec_generator.cli_command_parser.gradle_cli_command import GradleCLICommand, GradleCLIOptions
from macaron.errors import CommandLineParseError, PatchBuildCommandError

logger: logging.Logger = logging.getLogger(__name__)


GradleOptionPatchValueType = str | list[str] | bool | dict[str, str | None]


@dataclass
class GradleOptionalFlag(OptionDef[bool]):
    """This option represents an optional flag in Gradle CLI command.

    For example:
        - Has one short name -d/--debug
        - Has no short name --continue
        - Has multiple short names -?/-h/--help

    This option can have multiple values, and it's not required.
    """

    short_names: list[str] | None

    # Right now this is used for --continue and --help where the default attribute name for it
    # in the returned argparse.Namespace is "continue" which conflicts with a Python keyword and
    # "help" which conflicts with the built-in function help().
    dest: str | None = field(default=None)

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[bool]:
        """Return True if the provided patch value is compatible with the internal type of this option."""
        return isinstance(patch, bool)

    def add_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        kwargs: dict[str, Any] = {"action": "store_true"}
        if self.dest:
            kwargs["dest"] = self.dest

        if self.short_names:
            arg_parse.add_argument(
                *(self.short_names + [self.long_name]),
                **kwargs,
            )
        else:
            arg_parse.add_argument(
                self.long_name,
                **kwargs,
            )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "bool"


@dataclass
class GradleOptionalNegatableFlag(OptionDef[bool]):
    """This option represents an optional negatable flag in Gradle CLI command.

    For example: --build-cache/--no-build-cache
    """

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[bool]:
        """Return True if the provide patch value is compatible with the internal type of this option."""
        return isinstance(patch, bool)

    @staticmethod
    def get_negated_long_name(long_name: str) -> str:
        """Return the negated version of a long option name."""
        return f"--no-{long_name.removeprefix('--')}"

    def add_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        # We allow providing both the normal and negated form.
        negated_long_name = self.get_negated_long_name(self.long_name)
        dest = self.long_name.removeprefix("--").replace("-", "_")

        # We set the default to None so that we don't print out these options
        # if they are not provided in the original build command in to_cmd_tasks().
        arg_parse.add_argument(
            self.long_name,
            action="store_true",
            default=None,
            dest=dest,
        )

        arg_parse.add_argument(
            negated_long_name,
            action="store_false",
            default=None,
            dest=dest,
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "bool"


@dataclass
class GradleSingleValue(OptionDef[str]):
    """This option represents an option that takes a value in Gradle CLI command."""

    short_name: str | None

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[str]:
        """Return True if the provided patch value is compatible with the internal type of this option."""
        return isinstance(patch, str)

    def add_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        if self.short_name:
            arg_parse.add_argument(
                *(self.short_name, self.long_name),
            )
        else:
            arg_parse.add_argument(
                self.long_name,
            )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "str"


@dataclass
class GradleProperties(OptionDef[dict[str, str | None]]):
    """This option represents an option used to define property values of a Gradle CLI command.

    This option can be defined multiple times and the values are appended into a list of string in argparse.
    However, it's stored internally as a dictionary mapping between the system property name and its value.

    In Gradle there are 2 options of this type:
        - -D/--system-prop
        - -P/--project-prop
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
class GradleTask(OptionDef[list[str]]):
    """This option represents the positional task option in Gradle CLI command.

    argparse.Namespace stores this as a list of string. This is stored internally as a list of string.
    """

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[list[str]]:
        """Return True if the provided patch value is compatible with the internal type of this option."""
        return is_list_of_strs(patch)

    def add_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        # Doesn't require to allow cases like "gradle --help".
        arg_parse.add_argument(
            self.long_name,
            nargs="*",
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "list[str]"


@dataclass
class GradleAppendedList(OptionDef[list[str]]):
    """This option represents an option that can be specified multiple times.

    Each instance of the option will be appended to a list.
    For example, one can exclude multiple tasks with:
    gradle <task_to_run> --exclude-task taskA --exclude-task taskB
    """

    short_name: str

    def is_valid_patch_option(self, patch: Any) -> TypeGuard[list[str]]:
        """Return True if the provided patch value is compatible with the internal type of this option."""
        return is_list_of_strs(patch)

    def add_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        arg_parse.add_argument(
            *(self.short_name, self.long_name),
            action="append",
        )

    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        return "list[str]"


# TODO: some value options only allow you to provide certain values.
# For example: --console allows "plain", "auto", "rich" or "verbose".
# They are right now not enforced. We need to think whether we want to enforce them.
GRADLE_OPTION_DEF: list[OptionDef] = [
    GradleOptionalFlag(
        short_names=["-?", "-h"],
        long_name="--help",
        dest="help_",
    ),
    GradleOptionalFlag(
        short_names=["-a"],
        long_name="--no-rebuild",
    ),
    GradleOptionalFlag(
        short_names=None,
        long_name="--continue",
        dest="continue_",
    ),
    GradleOptionalFlag(
        short_names=["-d"],
        long_name="--debug",
    ),
    GradleOptionalFlag(
        short_names=None,
        long_name="--export-keys",
    ),
    GradleOptionalFlag(
        short_names=None,
        long_name="--foreground",
    ),
    GradleOptionalFlag(
        short_names=["-i"],
        long_name="--info",
    ),
    GradleOptionalFlag(
        short_names=None,
        long_name="--offline",
    ),
    GradleOptionalFlag(
        short_names=None,
        long_name="--profile",
    ),
    GradleOptionalFlag(
        short_names=["-q"],
        long_name="--quiet",
    ),
    GradleOptionalFlag(
        short_names=None,
        long_name="--refresh-dependencies",
    ),
    GradleOptionalFlag(
        short_names=None,
        long_name="--refresh-keys",
    ),
    GradleOptionalFlag(
        short_names=None,
        long_name="--rerun-tasks",
    ),
    GradleOptionalFlag(
        short_names=["-S"],
        long_name="--full-stacktrace",
    ),
    GradleOptionalFlag(
        short_names=["-s"],
        long_name="--stacktrace",
    ),
    GradleOptionalFlag(
        short_names=None,
        long_name="--status",
    ),
    GradleOptionalFlag(
        short_names=None,
        long_name="--stop",
    ),
    GradleOptionalFlag(
        short_names=["-t"],
        long_name="--continuous",
    ),
    GradleOptionalFlag(
        short_names=["-v"],
        long_name="--version",
    ),
    GradleOptionalFlag(
        short_names=["-w"],
        long_name="--warn",
    ),
    GradleOptionalFlag(
        short_names=None,
        long_name="--write-locks",
    ),
    GradleOptionalNegatableFlag(
        long_name="--build-cache",
    ),
    GradleOptionalNegatableFlag(
        long_name="--configuration-cache",
    ),
    GradleOptionalNegatableFlag(
        long_name="--configure-on-demand",
    ),
    GradleOptionalNegatableFlag(
        long_name="--daemon",
    ),
    GradleOptionalNegatableFlag(
        long_name="--parallel",
    ),
    GradleOptionalNegatableFlag(
        long_name="--scan",
    ),
    GradleOptionalNegatableFlag(
        long_name="--watch-fs",
    ),
    # This has been validated by setting up a minimal gradle project. Gradle version 8.14.2
    #     gradle init --type java-library
    # And use default values for any prompted configuration.
    # Then append this block of code into src/build.gradle
    #
    # task boo {
    #     doLast {
    #         println "Running task: boo"
    #     }
    # }
    # task foo {
    #     doLast {
    #         println "Running task: foo"
    #     }
    # }
    # task bar {
    #     doLast {
    #         println "Running task: bar"
    #     }
    # }
    # task everything(dependsOn: ['boo', 'foo']) {
    #     doLast {
    #         println "Running task: everything"
    #     }
    # }
    # And then run ./gradlew everything -x boo -x foo
    #   > Task :lib:bar
    #   Running task: gamma
    #   > Task :lib:everything
    #   Running task: everything
    GradleAppendedList(
        short_name="-x",
        long_name="--exclude-task",
    ),
    # TODO: determine which of these options can be provided multiple times.
    GradleSingleValue(
        short_name="-b",
        long_name="--build-file",
    ),
    GradleSingleValue(
        short_name="-c",
        long_name="--settings-file",
    ),
    GradleSingleValue(
        short_name=None,
        long_name="--configuration-cache-problems",
    ),
    GradleSingleValue(
        short_name=None,
        long_name="--console",
    ),
    GradleSingleValue(
        short_name="-F",
        long_name="--dependency-verification",
    ),
    GradleSingleValue(
        short_name="-g",
        long_name="--gradle-user-home",
    ),
    GradleSingleValue(
        short_name="-I",
        long_name="--init-script",
    ),
    GradleSingleValue(
        short_name=None,
        long_name="--include-build",
    ),
    GradleSingleValue(
        short_name="-M",
        long_name="--write-verification-metadata",
    ),
    GradleSingleValue(
        short_name=None,
        long_name="--max-workers",
    ),
    GradleSingleValue(
        short_name="-p",
        long_name="--project-dir",
    ),
    GradleSingleValue(
        short_name=None,
        long_name="--priority",
    ),
    GradleSingleValue(
        short_name=None,
        long_name="--project-cache-dir",
    ),
    GradleSingleValue(
        short_name=None,
        long_name="--update-locks",
    ),
    GradleSingleValue(
        short_name=None,
        long_name="--warning-mode",
    ),
    GradleProperties(
        short_name="-D",
        long_name="--system-prop",
    ),
    GradleProperties(
        short_name="-P",
        long_name="--project-prop",
    ),
    GradleTask(
        long_name="tasks",
    ),
]


class GradleCLICommandParser:
    """A Gradle CLI Command Parser."""

    ACCEPTABLE_EXECUTABLE = {"gradle", "gradlew"}

    def __init__(self) -> None:
        """Initialize the instance."""
        self.arg_parser = argparse.ArgumentParser(
            description="Parse Gradle CLI command",
            prog="gradle",
            add_help=False,
            # https://docs.python.org/3/library/argparse.html#exit-on-error
            # Best effort of parsing the build command. Therefore, we don't want to exit on error.
            exit_on_error=False,
        )

        # A mapping between the long name to its option definition.
        self.option_defs: dict[str, OptionDef] = {}

        for opt_def in GRADLE_OPTION_DEF:
            opt_def.add_to_arg_parser(self.arg_parser)

            self.option_defs[opt_def.long_name] = opt_def

        self.build_tool = PatchCommandBuildTool.GRADLE

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
        return os.path.basename(executable_path) in GradleCLICommandParser.ACCEPTABLE_EXECUTABLE

    def validate_patch(self, patch: Mapping[str, GradleOptionPatchValueType | None]) -> bool:
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

    def parse(self, cmd_list: list[str]) -> GradleCLICommand:
        """Parse the Gradle CLI Command.

        Parameters
        ----------
        cmd_list: list[str]
            The Gradle CLI Command as list of strings.

        Returns
        -------
        GradleCLICommand
            The GradleCLICommand instance.

        Raises
        ------
        CommandLineParseError
            If an error happens when parsing the Gradle CLI Command.
        """
        if not cmd_list:
            raise CommandLineParseError("The provided cmd list is empty.")

        exe_path = cmd_list[0]
        options = cmd_list[1:]

        if os.path.basename(exe_path) not in GradleCLICommandParser.ACCEPTABLE_EXECUTABLE:
            raise CommandLineParseError(f"{exe_path} is not an acceptable Gradle executable path.")

        # TODO: because our parser is not completed for all cases, should we be more relaxed and use
        # parse_unknown_options?
        try:
            parsed_opts = self.arg_parser.parse_args(options)
        except argparse.ArgumentError as error:
            raise CommandLineParseError(f"Failed to parse {' '.join(options)}.") from error
        # Even though we have set `exit_on_error`, argparse still exits unexpectedly in some
        # cases. This has been confirmed to be a bug in the argparse library implementation.
        # https://github.com/python/cpython/issues/121018.
        # This is fixed in Python3.12, but not Python3.11
        except SystemExit as sys_exit_err:
            raise CommandLineParseError(
                f"Failed to parse the Gradle CLI Options {' '.join(options)}."
            ) from sys_exit_err

        gradle_cli_options = GradleCLIOptions.from_parsed_arg(parsed_opts)

        return GradleCLICommand(
            executable=exe_path,
            options=gradle_cli_options,
        )

    def _patch_properties_mapping(
        self,
        original_props: dict[str, str],
        option_long_name: str,
        patch_value: GradleOptionPatchValueType,
    ) -> dict[str, str]:
        """
        Apply a patch value to an existing properties dictionary for a specified Gradle option.

        This function locates the metadata definition for the given option by its long name,
        ensures it is a properties-type option, validates the patch value type, and then
        applies the patch using `patch_mapping`. Throws a `PatchBuildCommandError` if the
        option is not valid or the patch value's type is incorrect.

        Parameters
        ----------
        original_props: dict[str, str]
            The original mapping of property names to values.
        option_long_name: str
            The long name of the Gradle option to patch.
        patch_value: GradleOptionPatchValueType
            The patch to apply to the properties mapping.

        Returns
        -------
        dict[str, str]
            The updated properties mapping after applying the patch.

        Raises
        ------
        PatchBuildCommandError
            If the option is not a valid properties-type option or the patch value does not have a valid type.
        """
        prop_opt_def = self.option_defs.get(option_long_name)
        if not prop_opt_def or not isinstance(prop_opt_def, GradleProperties):
            raise PatchBuildCommandError(f"{option_long_name} from the patch is not a property type option.")

        if not prop_opt_def.is_valid_patch_option(patch_value):
            raise PatchBuildCommandError(
                f"Incorrect runtime type for patch option {option_long_name}, value: {patch_value}."
            )

        return patch_mapping(
            original=original_props,
            patch=patch_value,
        )

    def apply_patch(
        self,
        cli_command: GradleCLICommand,
        patch_options: Mapping[str, GradleOptionPatchValueType | None],
    ) -> GradleCLICommand:
        """Patch the options of a Gradle CLI command, while persisting the executable path.

        `patch_options` is a mapping with:

        - **Key**: the long name of a Gradle CLI option as string. For example: ``--continue``, ``--build-cache``.
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
        cli_command : GradleCLICommand
            The original Gradle command, as a ``GradleCLICommand`` object from ``GradleCLICommandParser.parse(...)``
        patch_options : Mapping[str, GradleOptionPatchValueType | None]
            The patch values.

        Returns
        -------
        GradleCLICommand
            The patched command as a new ``GradleCLICommand`` object.

        Raises
        ------
        PatchBuildCommandError
            If an error happens during the patching process.
        """
        return GradleCLICommand(
            executable=cli_command.executable,
            options=self.apply_option_patch(
                cli_command.options,
                patch=patch_options,
            ),
        )

    def apply_option_patch(
        self,
        gradle_cli_options: GradleCLIOptions,
        patch: Mapping[str, GradleOptionPatchValueType | None],
    ) -> GradleCLIOptions:
        """Patch the Gradle CLI Options and return a new copy.

        Parameters
        ----------
        gradle_cli_options: GradleCLIOptions
            The Gradle CLI Options to patch.
        patch: Mapping[str, GradleOptionPatchValueType | None]
            A mapping between the name of the attribute in GradleCLIOptions and its patch value

        Returns
        -------
        GradleCLIOptions
            The new patched gradle cli options.

        Raises
        ------
        PatchBuildCommandError
            If an error happens during the patching process.
        """
        if not self.validate_patch(patch):
            raise PatchBuildCommandError("The patch is invalid.")

        # Copy the Maven CLI Options for patching.
        new_gradle_cli_options = deepcopy(gradle_cli_options)

        for option_long_name, patch_value in patch.items():
            if option_long_name == "--help":
                attr_name = "help_"
            elif option_long_name == "--continue":
                attr_name = "continue_"
            else:
                # Get the attribute name of GradleCLIOption object.
                # They all follow the same rule of removing the prefix --
                # from option long name and replace all "-" with "_"
                attr_name = option_long_name.removeprefix("--").replace("-", "_")

            # Ensure that setting any option to None in the patch
            # will remove it from the build command.
            if patch_value is None:
                setattr(new_gradle_cli_options, attr_name, patch_value)
                continue

            if option_long_name == "--project-prop":
                new_gradle_cli_options.project_prop = self._patch_properties_mapping(
                    original_props=new_gradle_cli_options.project_prop or {},
                    option_long_name=option_long_name,
                    patch_value=patch_value,
                )
                continue

            if option_long_name == "--system-prop":
                new_gradle_cli_options.system_prop = self._patch_properties_mapping(
                    original_props=new_gradle_cli_options.system_prop or {},
                    option_long_name=option_long_name,
                    patch_value=patch_value,
                )
                continue

            setattr(new_gradle_cli_options, attr_name, patch_value)

        return new_gradle_cli_options
