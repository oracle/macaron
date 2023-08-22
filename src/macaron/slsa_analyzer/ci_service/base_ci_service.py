# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BaseCIService class to be inherited by a CI service."""

import logging
import os
from abc import abstractmethod
from collections.abc import Iterable

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.parsers.bashparser import BashCommands
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

    @abstractmethod
    def extract_all_bash(self, callgraph: CallGraph, macaron_path: str = "") -> Iterable[BashCommands]:
        """Parse configurations to extract the bash scripts triggered by the CI service.

        Parameters
        ----------
        callgraph : CallGraph
            The call graph for this CI.
        macaron_path : str
            Macaron's root path (optional).

        Yields
        ------
        BashCommands
            The parsed bash script commands.
        """
        raise NotImplementedError

    def has_kws_in_config(self, kws: list, repo_path: str) -> tuple[str, str]:
        """Check the content of all config files in a repository for any build keywords.

        For now, it only checks the file content directly.

        Parameters
        ----------
        kws : list
            The list of keywords to check.
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
                                'Found build command %s at line %s in %s: "%s"',
                                keyword,
                                index,
                                config,
                                line.strip(),
                            )
                            return keyword, config
                logger.info("No build command found in %s", file_path)
                return "", ""
            except FileNotFoundError as error:
                logger.error(error)
                continue
        return "", ""

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        """Get the latest run of a workflow in the repository.

        This workflow run must be based on the latest commit according to the commit sha in the
        Analyze context.

        Parameters
        ----------
        repo_full_name : str
            The target repo's full name.
        branch_name : str
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

    def extract_all_bash(self, callgraph: CallGraph, macaron_path: str = "") -> Iterable[BashCommands]:
        """Parse configurations to extract the bash scripts triggered by the CI service.

        Parameters
        ----------
        callgraph : CallGraph
            The call graph for this CI.
        macaron_path : str
            Macaron's root path (optional).

        Yields
        ------
        BashCommands
            The parsed bash script commands.
        """
        return []

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        """Get the latest run of a workflow in the repository.

        This workflow run must be based on the latest commit according to the commit sha in the
        Analyze context.

        Parameters
        ----------
        repo_full_name : str
            The target repo's full name.
        branch_name : str
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
