# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the classes that represent components of a Maven CLI Command."""

import argparse
from typing import Any


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
            # If ele doesn't have "=", for example `-Dmaven.skip.test`, we store
            # the value as an empty string and don't try to evaluate it.
            #
            # For example:
            #   Maven evaluates the system property maven.skip.test to be "true" in these two commands
            #       mvn clean package -Dmaven.skip.test=true
            #       mvn clean package -Dmaven.skip.test
            #   However, we store -Dmaven.skip.test=true as {"maven.skip.test": "true"}
            #   and -Dmaven.skip.test as {"maven.skip.test": ""}
            #   To check how Maven evaluate the expression, run these commands on any project that uses maven.
            #       mvn help:evaluate -Dmaven.skip.test -Dexpression=maven.skip.test -q -DforceStdout
            #       mvn help:evaluate -Dmaven.skip.test=true -Dexpression=maven.skip.test -q -DforceStdout
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
