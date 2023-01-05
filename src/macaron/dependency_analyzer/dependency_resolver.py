# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module processes and collects the dependencies to be processed by Macaron."""

import logging
from abc import abstractmethod
from enum import Enum
from typing import TypedDict

from packaging import version

from macaron.config.target_config import Configuration
from macaron.output_reporter.results import SCMStatus
from macaron.slsa_analyzer.git_url import get_remote_vcs_url, get_repo_full_name_from_url

logger: logging.Logger = logging.getLogger(__name__)


class DependencyTools(str, Enum):
    """Dependency resolvers supported by Macaron."""

    CYCLONEDX_MAVEN = "cyclonedx-maven"


class DependencyInfo(TypedDict):
    """The information of a resolved Java dependency."""

    version: str
    group: str
    name: str
    url: str
    note: str
    available: SCMStatus


class DependencyAnalyzer:
    """This abstract class is used to implement dependency analyzers."""

    def __init__(self, resources_path: str, file_name: str, debug_path: str, tool_version: str) -> None:
        """Initialize the dependency analyzer instance.

        Parameters
        ----------
        resources_path : str
            The path to the resources directory.
        file_name : str
            The name of dependency output file.
        debug_path : str
            The file path where all the dependencies will be stored for debugging.
        tool_version : str
            The version of the dependency analyzer.
        """
        self.resources_path: str = resources_path
        self.file_name: str = file_name
        self.debug_path: str = debug_path
        self.tool_version: str = tool_version
        self.all_versions: dict = {}  # Stores all the versions of dependencies for debugging.
        self.latest_versions: dict[str, DependencyInfo] = {}  # Stores the latest version of dependencies.
        self.url_to_artifact: dict = {}  # Used to detect artifacts that have similar repos.
        self.submodules: set = set()  # Stores all the submodule dependencies.
        self.debug: bool = bool(debug_path)

    @abstractmethod
    def collect_dependencies(self, dir_path: str) -> dict[str, DependencyInfo]:
        """Process the dependency JSON files and collect direct dependencies.

        Parameters
        ----------
        dir_path : str
            Path to the repo.

        Returns
        -------
        dict[str, DependencyInfo]
            A dictionary where artifacts are grouped based on "artifactId:groupId".
        """
        raise NotImplementedError

    @abstractmethod
    def get_cmd(self) -> list:
        """Return the CLI command to run the dependency analyzer.

        Returns
        -------
        list
            The command line arguments.
        """
        raise NotImplementedError

    def _add_latest_version(
        self,
        item: DependencyInfo,
        key: str,
    ) -> None:
        """Find and add the unique URL for the latest version of the artifact.

        Parameters
        ----------
        item : DependencyInfo
            The dictionary containing info about the dependency to be added.
        key : str
            The ID of the artifact.
        """
        # Check if the URL is already seen for a different artifact.
        if item["url"] != "":
            artifacts = self.url_to_artifact.get(item["url"])
            if artifacts is None:
                self.url_to_artifact[item["url"]] = {key}
            else:
                item["note"] = f"{item['url']} is already analyzed."
                item["available"] = SCMStatus.DUPLICATED_SCM
                self.url_to_artifact[item["url"]].add_and_commit(key)
                logger.info(item["note"])
        else:
            logger.debug("Could not find SCM URL for %s. Skipping...", key)
            item["note"] = "Manual configuration required. Could not find SCM URL."
            item["available"] = SCMStatus.MISSING_SCM

        if self.debug:
            value = self.all_versions.get(key)
            if not value:
                self.all_versions[key] = [item]
            else:
                value.append(item)

        # Only update the artifact if it has a newer version.
        value = self.latest_versions.get(key)
        if not value:
            self.latest_versions[key] = item
        else:
            try:
                if (
                    value["version"]
                    and item["version"]
                    and version.Version(value["version"].lower()) < version.Version(item["version"].lower())
                ):
                    self.latest_versions[key] = item
            except ValueError as error:
                logger.error("Could not parse dependency version number: %s", error)

    @staticmethod
    def _find_valid_url(urls: list) -> str:
        """Find a valid URL from the list of URLs.

        Parameters
        ----------
        urls : list
            List of URLs.

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
