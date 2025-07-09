# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the classes that represent components of a Maven CLI Command."""

import argparse
from dataclasses import dataclass


@dataclass
class MavenCLIOptions:
    """The class that stores the values of options parsed from a Maven CLI Command."""

    # Optional flag.
    also_make: bool | None
    also_make_dependents: bool | None
    batch_mode: bool | None
    strict_checksums: bool | None
    lax_checksums: bool | None
    errors: bool | None
    fail_at_end: bool | None
    fail_fast: bool | None
    fail_never: bool | None
    help_: bool | None
    non_recursive: bool | None
    no_snapshot_updates: bool | None
    no_transfer_progress: bool | None
    quiet: bool | None
    version: bool | None
    show_version: bool | None
    debug: bool | None
    offline: bool | None
    update_snapshots: bool | None

    # Single Value Option.
    builder: str | None
    encrypt_master_password: str | None
    encrypt_password: str | None
    file: str | None
    global_settings: str | None
    global_toolchains: str | None
    log_file: str | None
    resume_from: str | None
    settings: str | None
    toolchains: str | None
    threads: str | None

    # Comma-delim list option.
    activate_profiles: list[str] | None
    projects: list[str] | None

    # System properties definition.
    define: dict[str, str] | None

    # Maven goals and plugin phases.
    goals: list[str] | None

    @classmethod
    def from_parsed_arg(
        cls,
        parsed_arg: argparse.Namespace,
    ) -> "MavenCLIOptions":
        """Initialize the instance from the the argparse.Namespace object.

        Parameters
        ----------
        parsed_arg : argparse.Namespace
            The argparse.Namespace object obtained from parsing the CLI Command.

        Returns
        -------
        MavenCLIOptions
            The MavenCLIOptions object.
        """
        return cls(
            also_make=parsed_arg.also_make,
            also_make_dependents=parsed_arg.also_make_dependents,
            batch_mode=parsed_arg.batch_mode,
            builder=parsed_arg.builder,
            strict_checksums=parsed_arg.strict_checksums,
            lax_checksums=parsed_arg.lax_checksums,
            define=MavenCLIOptions.parse_system_properties(parsed_arg.define) if parsed_arg.define else None,
            errors=parsed_arg.errors,
            encrypt_master_password=parsed_arg.encrypt_master_password,
            encrypt_password=parsed_arg.encrypt_password,
            file=parsed_arg.file,
            fail_at_end=parsed_arg.fail_at_end,
            fail_fast=parsed_arg.fail_fast,
            fail_never=parsed_arg.fail_never,
            global_settings=parsed_arg.global_settings,
            global_toolchains=parsed_arg.global_toolchains,
            help_=parsed_arg.help_,
            log_file=parsed_arg.log_file,
            non_recursive=parsed_arg.non_recursive,
            no_snapshot_updates=parsed_arg.no_snapshot_updates,
            no_transfer_progress=parsed_arg.no_transfer_progress,
            offline=parsed_arg.offline,
            activate_profiles=(
                MavenCLIOptions.parse_comma_sep_list(parsed_arg.activate_profiles)
                if parsed_arg.activate_profiles
                else None
            ),
            projects=MavenCLIOptions.parse_comma_sep_list(parsed_arg.projects) if parsed_arg.projects else None,
            quiet=parsed_arg.quiet,
            resume_from=parsed_arg.resume_from,
            settings=parsed_arg.settings,
            toolchains=parsed_arg.toolchains,
            threads=parsed_arg.threads,
            update_snapshots=parsed_arg.update_snapshots,
            version=parsed_arg.version,
            show_version=parsed_arg.show_version,
            debug=parsed_arg.debug,
            goals=parsed_arg.goals,
        )

    @staticmethod
    def parse_system_properties(props: list[str]) -> dict[str, str]:
        """Return a dictionary that maps between a system propertie and its value.

        Each property definition value in `props` can have either of these format:
        - `property=value` (e.g. `-Dproperty=value`): this will be parsed into a
        dictionary mapping of `"property": "value"`. Both the key and value
        of this mapping is of type string.
        - `property` (e.g. `-Dproperty`): this will be parsed into a dictionary mapping of `"property": "true"`.

        Parameters
        ----------
        props: list[str]
            The list of values provided to -D/--define in the cli command.
            This is the list parsed by argparse.

        Returns
        -------
        dict[str, str]:
            The system properties dictionary.

        Examples
        --------
        >>> MavenCLIOptions.parse_system_properties(["boo=true", "foo=1", "bar"])
        {'boo': 'true', 'foo': '1', 'bar': 'true'}
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
            # the value using the value "true" string.
            #
            # For example:
            #   Maven evaluates the system property maven.skip.test to be "true" in these two commands
            #       mvn clean package -Dmaven.skip.test=true
            #       mvn clean package -Dmaven.skip.test
            #   To check how Maven evaluate the expression, run these commands on any project that uses maven.
            #       mvn help:evaluate -Dmaven.skip.test -Dexpression=maven.skip.test -q -DforceStdout
            #       mvn help:evaluate -Dmaven.skip.test=true -Dexpression=maven.skip.test -q -DforceStdout
            if not prop_val:
                system_props[prop_name] = "true"
            else:
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

    def to_option_cmds(self) -> list[str]:
        """Return the options as a list of strings."""
        result = self.to_cmd_no_goals()
        if self.goals:
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

        if self.help_:
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


@dataclass
class MavenCLICommand:
    """The class that stores the values of a Maven CLI Command."""

    executable: str
    options: MavenCLIOptions

    def to_cmds(self) -> list[str]:
        """Return the CLI Command as a list of strings."""
        result = []
        result.append(self.executable)
        result.extend(self.options.to_option_cmds())
        return result
