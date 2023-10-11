# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module processes and collects the dependencies to be processed by Macaron."""

import logging
import os
import subprocess  # nosec B404
from abc import ABC, abstractmethod
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from typing import Any, TypedDict

from packageurl import PackageURL
from packaging import version

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.config.target_config import Configuration
from macaron.errors import MacaronError
from macaron.output_reporter.scm import SCMStatus
from macaron.repo_finder.repo_finder import find_repo
from macaron.slsa_analyzer.git_url import get_repo_full_name_from_url

logger: logging.Logger = logging.getLogger(__name__)


class DependencyTools(str, Enum):
    """Dependency resolvers supported by Macaron."""

    CYCLONEDX_MAVEN = "cyclonedx-maven"
    CYCLONEDX_GRADLE = "cyclonedx-gradle"


class DependencyInfo(TypedDict):
    """The information of a resolved dependency."""

    purl: PackageURL
    url: str
    note: str
    available: SCMStatus


class DependencyAnalyzerError(MacaronError):
    """The DependencyAnalyzer error class."""


class DependencyAnalyzer(ABC):
    """This abstract class is used to implement dependency analyzers."""

    def __init__(self, resources_path: str, file_name: str, tool_name: str, tool_version: str, repo_path: str) -> None:
        """Initialize the dependency analyzer instance.

        Parameters
        ----------
        resources_path : str
            The path to the resources directory.
        file_name : str
            The name of dependency output file.
        tool_name: str
            The name of the dependency analyzer.
        tool_version : str
            The version of the dependency analyzer.
        repo_path: str
            The path to the target repo.
        """
        self.resources_path: str = resources_path
        self.file_name: str = file_name
        self.tool_name: str = tool_name
        self.tool_version: str = tool_version
        self.repo_path: str = repo_path
        self.visited_deps: set = set()

    @abstractmethod
    def collect_dependencies(self, dir_path: str) -> dict[str, DependencyInfo]:
        """Process the dependency JSON files and collect direct dependencies.

        Parameters
        ----------
        dir_path : str
            Local path to the target repo.

        Returns
        -------
        dict
            A dictionary where artifacts are grouped based on "artifactId:groupId".
        """

    @abstractmethod
    def remove_sboms(self, dir_path: str) -> bool:
        """Remove all the SBOM files in the provided directory recursively.

        Parameters
        ----------
        dir_path : str
            Path to the repo.

        Returns
        -------
        bool
            Returns True if all the files are removed successfully.
        """

    @abstractmethod
    def get_cmd(self) -> list:
        """Return the CLI command to run the dependency analyzer.

        Returns
        -------
        list
            The command line arguments.
        """

    @staticmethod
    def add_latest_version(
        item: DependencyInfo,
        key: str,
        all_versions: dict[str, list[DependencyInfo]],
        latest_deps: dict[str, DependencyInfo],
        url_to_artifact: dict[str, set],
    ) -> None:
        """Find and add the unique URL for the latest version of the artifact.

        Parameters
        ----------
        item : DependencyInfo
            The dictionary containing info about the dependency to be added.
        key : str
            The ID of the artifact.
        all_versions: dict[str, str]
            Stores all the versions of dependencies for debugging.
        latest_deps: dict[str, DependencyInfo]
            Stores the latest version of dependencies.
        url_to_artifact: dict[str, set]
            Used to detect artifacts that have similar repos.
        """
        # Check if the URL is already seen for a different artifact.
        if item["url"] != "":
            artifacts = url_to_artifact.get(item["url"])
            if artifacts is None:
                url_to_artifact[item["url"]] = {key}
            else:
                item["note"] = f"{item['url']} is already analyzed."
                item["available"] = SCMStatus.DUPLICATED_SCM
                url_to_artifact[item["url"]].add(key)
                logger.debug(item["note"])
        else:
            logger.debug("Could not find SCM URL for %s. Skipping...", key)
            item["note"] = "Manual configuration required. Could not find SCM URL."
            item["available"] = SCMStatus.MISSING_SCM

        # For debugging purposes.
        value = all_versions.get(key)
        if not value:
            all_versions[key] = [item]
        else:
            value.append(item)

        # Only update the artifact if it has a newer version.
        latest_value = latest_deps.get(key)
        if not latest_value:
            latest_deps[key] = item
        else:
            try:
                # These are stored as variables so mypy does not complain about None values (union-attr)
                latest_value_purl = latest_value.get("purl")
                item_purl = item.get("purl")
                if (
                    latest_value_purl is not None
                    and item_purl is not None
                    and (latest_version := latest_value_purl.version)
                    and (item_version := item_purl.version)
                    and version.Version(latest_version) < version.Version(item_version)
                ):
                    latest_deps[key] = item
            except ValueError as error:
                logger.error("Could not parse dependency version number: %s", error)

    @staticmethod
    def merge_configs(
        config_deps: list[Configuration], resolved_deps: dict[str, DependencyInfo]
    ) -> list[Configuration]:
        """Merge the resolved dependencies into the manual config dependencies.

        Manual configuration entries are prioritized over the automatically resolved dependencies.

        Parameters
        ----------
        config_deps : list[Configuration]
            Dependencies defined in the configuration file.
        resolved_deps : dict[str, DependencyInfo]
            The automatically resolved dependencies.

        Returns
        -------
        list[Configuration]
            The result list contains the merged dependencies.
        """
        merged_deps: list[Configuration] = []
        if config_deps:
            for dep in config_deps:
                dep.set_value("available", SCMStatus.AVAILABLE)
                merged_deps.append(dep)

        if not resolved_deps:
            return merged_deps

        for key, value in resolved_deps.items():
            duplicate = False
            if config_deps:
                for m_dep in config_deps:
                    m_repo = get_repo_full_name_from_url(m_dep.get_value("path"))
                    a_repo = get_repo_full_name_from_url(value.get("url", ""))
                    if m_repo and m_repo == a_repo:
                        duplicate = True
                        break
                if duplicate:
                    continue
            merged_deps.append(
                Configuration(
                    {
                        "id": key,
                        "purl": str(value.get("purl")),
                        "path": value.get("url"),
                        "branch": "",
                        "digest": "",
                        "note": value.get("note"),
                        "available": value.get("available"),
                    }
                )
            )

        return merged_deps

    @staticmethod
    def tool_valid(tool: str) -> bool:
        """Validate the dependency analyzer name.

        Parameters
        ----------
        tool : str
            The full name of the dependency analyzer, i.e., <name>:<version>.

        Returns
        -------
        bool
            Return True if the tool name is valid.
        """
        if ":" not in tool:
            return False
        items = tool.split(":")
        supported = False
        for element in DependencyTools:
            if items[0] == element.value:
                supported = True
                break
        if not supported:
            logger.error("Dependency tool %s is not supported.", items[0])
            return False
        try:
            if not version.Version(items[1].lower()):
                logger.error("Invalid dependency analyzer version: %s", items[1])
                return False
        except ValueError as error:
            logger.error("Dependency analyzer: %s.", error)
            return False
        return True

    @staticmethod
    def resolve_dependencies(main_ctx: Any, sbom_path: str) -> dict[str, DependencyInfo]:
        """Resolve the dependencies of the main target repo.

        Parameters
        ----------
        main_ctx : Any (AnalyzeContext)
            The context of object of the target repository.
        sbom_path: str
            The path to the SBOM.

        Returns
        -------
        dict[str, DependencyInfo]
            A dictionary where artifacts are grouped based on ``artifactId:groupId``.
        """
        deps_resolved: dict[str, DependencyInfo] = {}

        if sbom_path:
            logger.info("Getting the dependencies from the SBOM defined at %s.", sbom_path)
            # Import here to avoid circular dependency
            # pylint: disable=import-outside-toplevel, cyclic-import
            from macaron.dependency_analyzer.cyclonedx import get_deps_from_sbom

            deps_resolved = get_deps_from_sbom(sbom_path)

            # Use repo finder to find more repositories to analyze.
            if defaults.getboolean("repofinder", "find_repos"):
                DependencyAnalyzer._resolve_more_dependencies(deps_resolved)

            return deps_resolved

        build_tools = main_ctx.dynamic_data["build_spec"]["tools"]
        if not build_tools:
            logger.info("Unable to find any valid build tools.")
            return {}

        # Grab dependencies for each build tool, collate all into the deps_resolved
        for build_tool in build_tools:
            try:
                dep_analyzer = build_tool.get_dep_analyzer(main_ctx.component.repository.fs_path)
            except DependencyAnalyzerError as error:
                logger.error("Unable to find a dependency analyzer for %s: %s", build_tool.name, error)
                return {}

            if isinstance(dep_analyzer, NoneDependencyAnalyzer):
                logger.info(
                    "Dependency analyzer is not available for %s",
                    build_tool.name,
                )
                return {}

            # Start resolving dependencies.
            logger.info(
                "Running %s version %s dependency analyzer on %s",
                dep_analyzer.tool_name,
                dep_analyzer.tool_version,
                main_ctx.component.repository.fs_path,
            )

            log_path = os.path.join(
                global_config.build_log_path,
                f"{main_ctx.component.report_file_name}.{dep_analyzer.tool_name}.log",
            )

            # Clean up existing SBOM files.
            dep_analyzer.remove_sboms(main_ctx.component.repository.fs_path)

            commands = dep_analyzer.get_cmd()
            working_dirs: Iterable[Path] = build_tool.get_build_dirs(main_ctx.component.repository.fs_path)
            for working_dir in working_dirs:
                # Get the absolute path to use as the working dir in the subprocess.
                working_dir = Path(main_ctx.component.repository.fs_path).joinpath(working_dir)

                try:
                    # Suppressing Bandit's B603 report because the repo paths are validated.
                    analyzer_output = subprocess.run(  # nosec B603
                        commands,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=True,
                        cwd=str(working_dir),
                        timeout=defaults.getint("dependency.resolver", "timeout", fallback=1200),
                    )
                    with open(log_path, mode="a", encoding="utf-8") as log_file:
                        log_file.write(analyzer_output.stdout.decode("utf-8"))

                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                    logger.error(error)
                    with open(log_path, mode="a", encoding="utf-8") as log_file:
                        log_file.write(error.output.decode("utf-8"))
                except FileNotFoundError as error:
                    logger.error(error)

                # We collect the generated SBOM as a best effort, even if the build exits with errors.
                # TODO: add improvements to help the SBOM build succeed as much as possible.
                deps_resolved |= dep_analyzer.collect_dependencies(str(working_dir))

            logger.info("Stored dependency resolver log for %s to %s.", dep_analyzer.tool_name, log_path)

        # Use repo finder to find more repositories to analyze.
        if defaults.getboolean("repofinder", "find_repos"):
            DependencyAnalyzer._resolve_more_dependencies(deps_resolved)

        return deps_resolved

    @staticmethod
    def _resolve_more_dependencies(dependencies: dict[str, DependencyInfo]) -> None:
        """Utilise the Repo Finder to resolve the repositories of more dependencies."""
        for item in dependencies.values():
            if item["available"] != SCMStatus.MISSING_SCM:
                continue

            item["url"] = find_repo(item["purl"])
            if item["url"] == "":
                logger.debug("Failed to find url for purl: %s", item["purl"])
            else:
                # TODO decide how to handle possible duplicates here
                item["available"] = SCMStatus.AVAILABLE
                item["note"] = ""


class NoneDependencyAnalyzer(DependencyAnalyzer):
    """This class is used to implement an empty dependency analyzers."""

    def __init__(self) -> None:
        """Initialize the dependency analyzer instance."""
        super().__init__(resources_path="", file_name="", tool_name="", tool_version="", repo_path="")

    def collect_dependencies(self, dir_path: str) -> dict[str, DependencyInfo]:
        """Process the dependency JSON files and collect direct dependencies.

        Parameters
        ----------
        dir_path : str
            Local path to the target repo.

        Returns
        -------
        dict
            A dictionary where artifacts are grouped based on "artifactId:groupId".
        """
        return {}

    def remove_sboms(self, dir_path: str) -> bool:
        """Remove all the SBOM files in the provided directory recursively.

        Parameters
        ----------
        dir_path : str
            Path to the repo.

        Returns
        -------
        bool
            Returns True if all the files are removed successfully.
        """
        return False

    def get_cmd(self) -> list:
        """Return the CLI command to run the dependency analyzer.

        Returns
        -------
        list
            The command line arguments.
        """
        return []
