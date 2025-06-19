# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the classes that represent components of a Gradle CLI Command."""

import argparse
from typing import Any


class GradleCLIOptions:
    """The class that stores the values of options parsed from a Gradle CLI Command."""

    def __init__(
        self,
        parsed_arg: argparse.Namespace,
    ):
        """Initialize the instance.

        Parameters
        ----------
        parsed_arg : argparse.Namespace
            The argparse.Namespace object obtained from parsing the CLI Command.
        """
        self.help: bool | None = parsed_arg.help
        self.no_rebuild: bool | None = parsed_arg.no_rebuild
        self._continue: bool | None = parsed_arg._continue
        self.debug: bool | None = parsed_arg.debug
        self.export_keys: bool | None = parsed_arg.export_keys
        self.foreground: bool | None = parsed_arg.foreground
        self.info: bool | None = parsed_arg.info
        self.offline: bool | None = parsed_arg.offline
        self.profile: bool | None = parsed_arg.profile
        self.quiet: bool | None = parsed_arg.quiet
        self.refresh_dependencies: bool | None = parsed_arg.refresh_dependencies
        self.refresh_keys: bool | None = parsed_arg.refresh_keys
        self.rerun_tasks: bool | None = parsed_arg.rerun_tasks
        self.full_stacktrace: bool | None = parsed_arg.full_stacktrace
        self.stacktrace: bool | None = parsed_arg.stacktrace
        self.status: bool | None = parsed_arg.status
        self.stop: bool | None = parsed_arg.stop
        self.continuous: bool | None = parsed_arg.continuous
        self.version: bool | None = parsed_arg.version
        self.warn: bool | None = parsed_arg.warn
        self.write_locks: bool | None = parsed_arg.write_locks
        self.build_cache: bool | None = parsed_arg.build_cache
        self.configuration_cache: bool | None = parsed_arg.configuration_cache
        self.configure_on_demand: bool | None = parsed_arg.configure_on_demand
        self.daemon: bool | None = parsed_arg.daemon
        self.parallel: bool | None = parsed_arg.parallel
        self.scan: bool | None = parsed_arg.scan
        self.watch_fs: bool | None = parsed_arg.watch_fs
        self.build_file: str | None = parsed_arg.build_file
        self.settings_file: str | None = parsed_arg.settings_file
        self.configuration_cache_problems: str | None = parsed_arg.configuration_cache_problems
        self.gradle_user_home: str | None = parsed_arg.gradle_user_home
        self.init_script: str | None = parsed_arg.init_script
        self.include_build: str | None = parsed_arg.include_build
        self.write_verification_metadata: str | None = parsed_arg.write_verification_metadata
        self.max_workers: str | None = parsed_arg.max_workers
        self.project_dir: str | None = parsed_arg.project_dir
        self.priority: str | None = parsed_arg.priority
        self.project_cache_dir: str | None = parsed_arg.project_cache_dir
        self.update_locks: str | None = parsed_arg.update_locks
        self.warning_mode: str | None = parsed_arg.warning_mode
        self.exclude_task: list[str] | None = parsed_arg.exclude_task
        self.system_prop: dict[str, str] | None = (
            GradleCLIOptions.parse_properties(parsed_arg.system_prop) if parsed_arg.system_prop else None
        )
        self.project_prop: dict[str, str] | None = (
            GradleCLIOptions.parse_properties(parsed_arg.project_prop) if parsed_arg.project_prop else None
        )
        self.tasks: list[str] | None = parsed_arg.tasks

    @staticmethod
    def parse_properties(props: list[str]) -> dict[str, str]:
        """Return a dictionary that maps between a property and its value.

        Each property definition value in `props` can have either of these format:
        - `property=value` (e.g. `property=value` from `-Dproperty=value`): this will
        be parsed into a dictionary mapping of `"property": "value"`.
        Both the key and value of this mapping is of type string.
        - `property` (e.g. `property` from `-Dproperty`): this will be parsed into a
        dictionary mapping of `"property": <empty_string>`.

        Parameters
        ----------
        props: list[str]
            The list of properties definition provided in the cli command.
            This is the list parsed by argparse.

        Returns
        -------
        dict[str, str]:
            The properties dictionary.

        Examples
        --------
        >>> GradleCLIOptions.parse_properties(["boo=true", "foo=1", "bar"])
        {'boo': 'true', 'foo': '1', 'bar': ''}
        """
        system_props = {}
        for ele in props:
            prop_name, _, prop_val = ele.partition("=")

            if not prop_val:
                system_props[prop_name] = ""
            else:
                system_props[prop_name] = prop_val

        return system_props

    def __eq__(self, value: Any) -> bool:
        if not isinstance(value, GradleCLIOptions):
            return False

        return vars(self) == vars(value)

    def to_cmd_tasks(self) -> list[str]:
        """Return the tasks and options as a list of string.

        Only enabled options are returned.

        Returns
        -------
        list[str]
            The tasks and options.
        """
        result = self.to_cmd_no_tasks()
        if self.tasks:
            for task in self.tasks:
                result.append(task)

        return result

    def to_cmd_no_tasks(self) -> list[str]:
        """Return the options only as a list of string.

        Only enabled options are returned.

        Returns
        -------
        list[str]
            The enabled options.
        """
        result = []

        if self.help:
            result.append("-h")

        if self.no_rebuild:
            result.append("-a")

        if self._continue:
            result.append("--continue")

        if self.debug:
            result.append("-d")

        if self.export_keys:
            result.append("--export-keys")

        if self.foreground:
            result.append("--foreground")

        if self.info:
            result.append("-i")

        if self.offline:
            result.append("--offline")

        if self.profile:
            result.append("--profile")

        if self.quiet:
            result.append("-q")

        if self.refresh_dependencies:
            result.append("--refresh-dependencies")

        if self.refresh_keys:
            result.append("--refresh-keys")

        if self.rerun_tasks:
            result.append("--rerun-tasks")

        if self.full_stacktrace:
            result.append("-S")

        if self.stacktrace:
            result.append("-s")

        if self.status:
            result.append("--status")

        if self.stop:
            result.append("--stop")

        if self.continuous:
            result.append("-t")

        if self.version:
            result.append("-v")

        if self.warn:
            result.append("-w")

        if self.write_locks:
            result.append("--write-locks")

        if self.build_cache is not None:
            if self.build_cache is True:
                result.append("--build-cache")
            else:
                result.append("--no-build-cache")

        if self.configuration_cache is not None:
            if self.configuration_cache is True:
                result.append("--configuration-cache")
            else:
                result.append("--no-configuration-cache")

        if self.configure_on_demand is not None:
            if self.configure_on_demand is True:
                result.append("--configure-on-demand")
            else:
                result.append("--no-configure-on-demand")

        if self.daemon is not None:
            if self.daemon is True:
                result.append("--daemon")
            else:
                result.append("--no-daemon")

        if self.parallel is not None:
            if self.parallel is True:
                result.append("--parallel")
            else:
                result.append("--no-parallel")

        if self.scan is not None:
            if self.scan is True:
                result.append("--scan")
            else:
                result.append("--no-scan")

        if self.watch_fs is not None:
            if self.watch_fs is True:
                result.append("--watch-fs")
            else:
                result.append("--no-watch-fs")

        if self.build_file:
            result.append("-b")
            result.append(self.build_file)

        if self.settings_file:
            result.append("-c")
            result.append(self.settings_file)

        if self.configuration_cache_problems:
            result.append("--configuration-cache-problems")
            result.append(self.configuration_cache_problems)

        if self.gradle_user_home:
            result.append("-g")
            result.append(self.gradle_user_home)

        if self.init_script:
            result.append("-I")
            result.append(self.init_script)

        if self.include_build:
            result.append("--include-build")
            result.append(self.include_build)

        if self.write_verification_metadata:
            result.append("-M")
            result.append(self.write_verification_metadata)

        if self.max_workers:
            result.append("--max-workers")
            result.append(self.max_workers)

        if self.project_dir:
            result.append("-p")
            result.append(self.project_dir)

        if self.priority:
            result.append("--priority")
            result.append(self.priority)

        if self.project_cache_dir:
            result.append("--project-cache-dir")
            result.append(self.project_cache_dir)

        if self.update_locks:
            result.append("--update-locks")
            result.append(self.update_locks)

        if self.warning_mode:
            result.append("--warning-mode")
            result.append(self.warning_mode)

        if self.exclude_task:
            for task in self.exclude_task:
                result.append("-x")
                result.append(task)

        if self.system_prop:
            for key, value in self.system_prop.items():
                if value:
                    result.append(f"-D{key}={value}")
                else:
                    result.append(f"-D{key}")

        if self.project_prop:
            for key, value in self.project_prop.items():
                if value:
                    result.append(f"-P{key}={value}")
                else:
                    result.append(f"-D{key}")

        return result


class GradleCLICommand:
    """The class that stores the values of a Gradle CLI Command."""

    def __init__(
        self,
        executable: str,
        options: GradleCLIOptions,
    ) -> None:
        """Initialize the instance.

        Parameters
        ----------
        executeable : str
            The executable part of the build command (e.g. mvnw, mvn or ./path/to/mvnw).

        options: GradleCLIOptions
            The GradleCLIOptions object created from parsing the options part of the build command.
        """
        self.executable = executable
        self.options = options

    def __eq__(self, value: Any) -> bool:
        if not isinstance(value, GradleCLICommand):
            return False

        return self.executable == value.executable and self.options == value.options
