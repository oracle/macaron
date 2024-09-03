# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BaseCIService class to be inherited by a CI service."""

import logging
import os
from abc import abstractmethod
from collections.abc import Iterable
from datetime import datetime

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.errors import CallGraphError
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, BuildToolCommand
from macaron.slsa_analyzer.git_service.api_client import BaseAPIClient
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService

logger: logging.Logger = logging.getLogger(__name__)


class BaseCIService:
    """This abstract class is used to implement CI services."""

    def __init__(self, name: str) -> None:
        """Initialize instance.

        Parameters
        ----------
        name : str
            The name of the CI service.
        """
        self.name = name
        self.entry_conf: list[str] = []  # The file or dir that determines a CI service.
        self.api_client: BaseAPIClient = BaseAPIClient()

    def __str__(self) -> str:
        return self.name

    @abstractmethod
    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        raise NotImplementedError

    @abstractmethod
    def set_api_client(self) -> None:
        """Set the API client using the personal access token."""
        raise NotImplementedError

    @abstractmethod
    def get_workflows(self, repo_path: str) -> list:
        """Get all workflows in a repository.

        Parameters
        ----------
        repo_path : str
            The path to the repository.

        Returns
        -------
        list
            The list of workflow files in this repository.
        """
        raise NotImplementedError

    def is_detected(
        self, repo_path: str, git_service: BaseGitService | None = None  # pylint: disable=unused-argument
    ) -> bool:
        """Return True if this CI service is used in the target repo.

        Parameters
        ----------
        repo_path : str
            The path to the target repo.

        git_service : BaseGitService
            The Git service that hosts the target repo (currently an unused argument).

        Returns
        -------
        bool
            True if this CI service is detected, else False.
        """
        exists = False
        logger.debug("Checking config files of CI Service: %s", self.name)
        for conf in self.entry_conf:
            config_path = os.path.join(repo_path, conf)
            if not os.path.isfile(config_path):
                logger.debug("%s does not exist in this repository.", conf)
                continue

            exists = True
        return exists

    @abstractmethod
    def build_call_graph(self, repo_path: str, macaron_path: str = "") -> CallGraph:
        """Build the call Graph for this CI service.

        Parameters
        ----------
        repo_path : str
            The path to the repo.
        macaron_path : str
            Macaron's root path (optional).

        Returns
        -------
        CallGraph : CallGraph
            The call graph built for the CI.
        """
        raise NotImplementedError

    def has_kws_in_config(self, kws: list, build_tool_name: str, repo_path: str) -> tuple[str, str]:
        """Check the content of all config files in a repository for any build keywords.

        For now, it only checks the file content directly.

        Parameters
        ----------
        kws : list
            The list of keywords to check.
        build_tool_name: str
            The name of the target build tool.
        repo_path : str
            The path to the target repo.

        Returns
        -------
        tuple[keyword, config]
            keyword : str
                The keyword that was found.
            config : str
                The config file name that the keyword was found in.
        """
        for config in self.entry_conf:
            file_path = os.path.join(repo_path, config)
            logger.debug("Checking kws for %s", file_path)
            try:
                with open(file_path, encoding="utf-8") as file:
                    for index, line in enumerate(file):
                        if any((keyword := kw) in line for kw in kws):
                            logger.info(
                                'Found build command %s for %s at line %s in %s: "%s"',
                                keyword,
                                build_tool_name,
                                index,
                                config,
                                line.strip(),
                            )
                            return keyword, config
                logger.info("No build command found for %s in %s", build_tool_name, file_path)
                return "", ""
            except FileNotFoundError as error:
                logger.debug(error)
                continue
        return "", ""

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str | None, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        """Get the latest run of a workflow in the repository.

        This workflow run must be based on the latest commit according to the commit sha in the
        Analyze context.

        Parameters
        ----------
        repo_full_name : str
            The target repo's full name.
        branch_name : str | None
            The target branch.
        commit_sha : str
            The commit sha of the target repo.
        commit_date : str
            The commit date of the target repo.
        workflow : str
            The name of the workflow file (e.g `build.yml`).

        Returns
        -------
        str
            The feed back of the check, or empty if no passing workflow is found.
        """
        raise NotImplementedError

    # pylint: disable=unused-argument
    def workflow_run_in_date_time_range(
        self,
        repo_full_name: str,
        workflow: str,
        publish_date_time: datetime,
        commit_date_time: datetime,
        job_id: str,
        step_name: str | None,
        step_id: str | None,
        time_range: int = 0,
        callee_node_type: str | None = None,
    ) -> set[str]:
        """Check if the repository has a workflow run started before the date_time timestamp within the time_range.

        - This method queries the list of workflow runs using the GitHub API for the provided repository full name.
        - It will filter out the runs that are not triggered by the given workflow.
        - It will only accept the runs that from `date_time - time_range` to `date_time`.
        - If a `step_name` is provided, checks that it has started before the `date_time` and has succeeded.

        Parameters
        ----------
        repo_full_name : str
            The target repo's full name.
        workflow : str
            The workflow URL.
        publish_date_time: datetime
            The artifact publishing datetime object.
        commit_date_time: datetime
            The artifact's source-code commit datetime object.
        job_id:str
            The job that triggers the run.
        step_name: str
            The step in the GitHub Action workflow that needs to be checked.
        time_range: int
            The date-time range in seconds. The default value is 0.
            For example a 30 seconds range for 2022-11-05T20:30 is 2022-11-05T20:15..2022-11-05T20:45.

        Returns
        -------
        set[str]
            The set of URLs found for the workflow within the time range.
        """
        return set()

    def workflow_run_deleted(self, timestamp: datetime) -> bool:
        """
        Check if the CI run data is deleted based on a retention policy.

        Parameters
        ----------
        timestamp: datetime
            The timestamp of the CI run.

        Returns
        -------
        bool
            True if the CI run data is deleted.
        """
        return False

    def get_build_tool_commands(self, callgraph: CallGraph, build_tool: BaseBuildTool) -> Iterable[BuildToolCommand]:
        """
        Traverse the callgraph and find all the reachable build tool commands.

        Parameters
        ----------
        callgraph: CallGraph
            The callgraph reachable from the CI workflows.
        build_tool: BaseBuildTool
            The corresponding build tool for which shell commands need to be detected.

        Yields
        ------
        BuildToolCommand
            The object that contains the build command as well useful contextual information.

        Raises
        ------
        CallGraphError
            Error raised when an error occurs while traversing the callgraph.
        """
        # By default we assume that there is no callgraph available for a CI service.
        # Each CI service should override this method if a callgraph is generated for it.
        raise CallGraphError("There is no callgraph for this CI service.")

    def get_third_party_configurations(self) -> list[str]:
        """Get the list of third-party CI configuration files.

        Returns
        -------
        list[str]
            The list of third-party CI configuration files
        """
        return []


class NoneCIService(BaseCIService):
    """This class can be used to initialize an empty CI service."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="")

    def get_workflows(self, repo_path: str) -> list:
        """Get all workflows in a repository.

        Parameters
        ----------
        repo_path : str
            The path to the repository.

        Returns
        -------
        list
            The list of workflow files in this repository.
        """
        return []

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""

    def set_api_client(self) -> None:
        """Set the API client using the personal access token."""

    def build_call_graph(self, repo_path: str, macaron_path: str = "") -> CallGraph:
        """Build the call Graph for this CI service.

        Parameters
        ----------
        repo_path : str
            The path to the repo.
        macaron_path : str
            Macaron's root path (optional).

        Returns
        -------
        CallGraph : CallGraph
            The call graph built for the CI.
        """
        return CallGraph(BaseNode(), "")

    def get_build_tool_commands(self, callgraph: CallGraph, build_tool: BaseBuildTool) -> Iterable[BuildToolCommand]:
        """
        Traverse the callgraph and find all the reachable build tool commands.

        Parameters
        ----------
        callgraph: CallGraph
            The callgraph reachable from the CI workflows.
        build_tool: BaseBuildTool
            The corresponding build tool for which shell commands need to be detected.

        Yields
        ------
        BuildToolCommand
            The object that contains the build command as well useful contextual information.

        Raises
        ------
        CallGraphError
            Error raised when an error occurs while traversing the callgraph.
        """
        raise CallGraphError("There is no callgraph for this CI service.")

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str | None, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        """Get the latest run of a workflow in the repository.

        This workflow run must be based on the latest commit according to the commit sha in the
        Analyze context.

        Parameters
        ----------
        repo_full_name : str
            The target repo's full name.
        branch_name : str | None
            The target branch.
        commit_sha : str
            The commit sha of the target repo.
        commit_date : str
            The commit date of the target repo.
        workflow : str
            The name of the workflow file (e.g `build.yml`).

        Returns
        -------
        str
            The feed back of the check, or empty if no passing workflow is found.
        """
        return ""

    def get_third_party_configurations(self) -> list[str]:
        """Get the list of third-party CI configuration files.

        Returns
        -------
        list[str]
            The list of third-party CI configuration files
        """
        return []
