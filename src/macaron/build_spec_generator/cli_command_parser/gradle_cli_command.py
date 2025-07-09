# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the classes that represent components of a Gradle CLI Command."""

import argparse
from dataclasses import dataclass


@dataclass
class GradleCLIOptions:
    """The class that stores the values of options parsed from a Gradle CLI Command."""

    # Optional flags with a different attribute name.
    continue_: bool | None
    help_: bool | None

    # Optional flags.
    no_rebuild: bool | None
    debug: bool | None
    export_keys: bool | None
    foreground: bool | None
    info: bool | None
    offline: bool | None
    profile: bool | None
    quiet: bool | None
    refresh_dependencies: bool | None
    refresh_keys: bool | None
    rerun_tasks: bool | None
    full_stacktrace: bool | None
    stacktrace: bool | None
    status: bool | None
    stop: bool | None
    continuous: bool | None
    version: bool | None
    warn: bool | None
    write_locks: bool | None
    build_cache: bool | None
    configuration_cache: bool | None
    configure_on_demand: bool | None
    daemon: bool | None
    parallel: bool | None
    scan: bool | None
    watch_fs: bool | None

    # Single value options.
    build_file: str | None
    settings_file: str | None
    configuration_cache_problems: str | None
    gradle_user_home: str | None
    init_script: str | None
    include_build: str | None
    write_verification_metadata: str | None
    max_workers: str | None
    project_dir: str | None
    priority: str | None
    project_cache_dir: str | None
    update_locks: str | None
    warning_mode: str | None

    # Appended list option.
    exclude_task: list[str] | None

    # Property definition options.
    system_prop: dict[str, str] | None
    project_prop: dict[str, str] | None

    # Gradle tasks.
    tasks: list[str] | None

    @classmethod
    def from_parsed_arg(
        cls,
        parsed_arg: argparse.Namespace,
    ) -> "GradleCLIOptions":
        """Initialize the instance from an argparse.Namespace object.

        Parameters
        ----------
        parsed_arg : argparse.Namespace
            The argparse.Namespace object obtained from parsing the CLI Command.

        Returns
        -------
        GradleCLIOptions
            The intialized GradleCLIOptions object instance.
        """
        return cls(
            help_=parsed_arg.help_,
            no_rebuild=parsed_arg.no_rebuild,
            continue_=parsed_arg.continue_,
            debug=parsed_arg.debug,
            export_keys=parsed_arg.export_keys,
            foreground=parsed_arg.foreground,
            info=parsed_arg.info,
            offline=parsed_arg.offline,
            profile=parsed_arg.profile,
            quiet=parsed_arg.quiet,
            refresh_dependencies=parsed_arg.refresh_dependencies,
            refresh_keys=parsed_arg.refresh_keys,
            rerun_tasks=parsed_arg.rerun_tasks,
            full_stacktrace=parsed_arg.full_stacktrace,
            stacktrace=parsed_arg.stacktrace,
            status=parsed_arg.status,
            stop=parsed_arg.stop,
            continuous=parsed_arg.continuous,
            version=parsed_arg.version,
            warn=parsed_arg.warn,
            write_locks=parsed_arg.write_locks,
            build_cache=parsed_arg.build_cache,
            configuration_cache=parsed_arg.configuration_cache,
            configure_on_demand=parsed_arg.configure_on_demand,
            daemon=parsed_arg.daemon,
            parallel=parsed_arg.parallel,
            scan=parsed_arg.scan,
            watch_fs=parsed_arg.watch_fs,
            build_file=parsed_arg.build_file,
            settings_file=parsed_arg.settings_file,
            configuration_cache_problems=parsed_arg.configuration_cache_problems,
            gradle_user_home=parsed_arg.gradle_user_home,
            init_script=parsed_arg.init_script,
            include_build=parsed_arg.include_build,
            write_verification_metadata=parsed_arg.write_verification_metadata,
            max_workers=parsed_arg.max_workers,
            project_dir=parsed_arg.project_dir,
            priority=parsed_arg.priority,
            project_cache_dir=parsed_arg.project_cache_dir,
            update_locks=parsed_arg.update_locks,
            warning_mode=parsed_arg.warning_mode,
            exclude_task=parsed_arg.exclude_task,
            system_prop=GradleCLIOptions.parse_properties(parsed_arg.system_prop) if parsed_arg.system_prop else None,
            project_prop=(
                GradleCLIOptions.parse_properties(parsed_arg.project_prop) if parsed_arg.project_prop else None
            ),
            tasks=parsed_arg.tasks,
        )

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

    def to_option_cmds(self) -> list[str]:
        """Return the options as a list of strings."""
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

        if self.help_:
            result.append("-h")

        if self.no_rebuild:
            result.append("-a")

        if self.continue_:
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
                    result.append(f"-P{key}")

        return result


@dataclass
class GradleCLICommand:
    """The class that stores the values of a Gradle CLI Command."""

    executable: str
    options: GradleCLIOptions

    def to_cmds(self) -> list[str]:
        """Return the CLI Command as a list of strings."""
        result = []
        result.append(self.executable)
        result.extend(self.options.to_option_cmds())
        return result
