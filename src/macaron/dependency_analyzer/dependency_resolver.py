# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module processes and collects the dependencies to be processed by Macaron."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from enum import Enum
from typing import TypedDict

from packaging import version

from macaron.config.defaults import defaults
from macaron.config.target_config import Configuration
from macaron.dependency_analyzer.java_repo_finder import find_java_repo
from macaron.errors import MacaronError
from macaron.output_reporter.scm import SCMStatus
from macaron.slsa_analyzer.git_url import get_remote_vcs_url, get_repo_full_name_from_url

logger: logging.Logger = logging.getLogger(__name__)


class DependencyTools(str, Enum):
    """Dependency resolvers supported by Macaron."""

    CYCLONEDX_MAVEN = "cyclonedx-maven"
    CYCLONEDX_GRADLE = "cyclonedx-gradle"


class DependencyInfo(TypedDict):
    """The information of a resolved dependency."""

    version: str
    group: str
    name: str
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
        if defaults.getboolean("repofinder.java", "find_repos"):
            DependencyAnalyzer._find_repo(item)

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
                if (
                    (latest_version := latest_value.get("version"))
                    and (item_version := item.get("version"))
                    and version.Version(latest_version) < version.Version(item_version)
                ):
                    latest_deps[key] = item
            except ValueError as error:
                logger.error("Could not parse dependency version number: %s", error)

    @staticmethod
    def _find_repo(item: DependencyInfo) -> None:
        if item["url"] != "" or item["version"] == "unspecified" or not item["group"] or not item["name"]:
            logger.debug("Item URL already exists, or item is missing information: %s", item)
            return
        gav = f"{item['group']}:{item['name']}:{item['version']}"
        if f"{item['group']}:{item['name']}" in defaults.get_list("repofinder.java", "ga_ignore_list"):
            logger.debug("Skipping GAV: %s", gav)
            return

        urls = find_java_repo(
            item["group"],
            item["name"],
            item["version"],
            defaults.get_list("repofinder.java", "repo_pom_paths"),
        )
        item["url"] = DependencyAnalyzer.find_valid_url(list(urls))
        if item["url"] == "":
            logger.debug("Failed to find url for GAV: %s", gav)

    @staticmethod
    def find_valid_url(urls: Iterable[str]) -> str:
        """Find a valid URL from the provided URLs.

        Parameters
        ----------
        urls : Iterable[str]
            An Iterable object containing urls.

        Returns
        -------
        str
            A valid URL or empty if it can't find any valid URL.
        """
        vcs_set = {get_remote_vcs_url(value) for value in urls if get_remote_vcs_url(value) != ""}

        # To avoid non-deterministic results we sort the URLs.
        vcs_list = sorted(vcs_set)

        if len(vcs_list) < 1:
            return ""

        # Report the first valid URL.
        return vcs_list.pop()

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
