# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module analyze Circle CI."""

from collections.abc import Iterable

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.config.defaults import defaults
from macaron.parsers.bashparser import BashCommands
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService


class CircleCI(BaseCIService):
    """This class implements CircleCI service."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="circle_ci")
        self.entry_conf = [".circleci/config.yml"]

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
        if "ci.circle_ci" in defaults:
            for item in defaults["ci.circle_ci"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("ci.circle_ci", item))

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
