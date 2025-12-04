# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module analyzes Jenkins CI."""

from __future__ import annotations

import glob
import logging
import os
import re

from macaron.code_analyzer.dataflow_analysis.analysis import analyse_bash_script
from macaron.code_analyzer.dataflow_analysis.core import Node, NodeForest
from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService

logger: logging.Logger = logging.getLogger(__name__)


class Jenkins(BaseCIService):
    """This class implements Jenkins CI service."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="jenkins")
        self.entry_conf = ["Jenkinsfile"]

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
        if not self.is_detected(repo_path=repo_path):
            logger.debug("There are no Jenkinsfile configurations.")
            return []

        workflow_files = []
        for conf in self.entry_conf:
            workflows = glob.glob(os.path.join(repo_path, conf))
            if workflows:
                logger.debug("Found Jenkinsfile configuration.")
                workflow_files.extend(workflows)
        return workflow_files

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        if "ci.jenkins" in defaults:
            for item in defaults["ci.jenkins"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("ci.jenkins", item))

    def set_api_client(self) -> None:
        """Set the API client using the personal access token."""

    def build_call_graph(self, repo_path: str, macaron_path: str = "") -> NodeForest:
        """Build the call Graph for this CI service.

        Parameters
        ----------
        repo_path : str
            The path to the repo.
        macaron_path : str
            Macaron's root path (optional).

        Returns
        -------
        NodeForest : NodeForest
            The call graph built for the CI.
        """
        if not macaron_path:
            macaron_path = global_config.macaron_path

        # # To match lines that start with sh '' or sh ''' ''' (either single or triple quotes)
        # # TODO: we need to support multi-line cases.
        pattern = r"^\s*sh\s+'{1,3}(.*?)'{1,3}$"
        workflow_files = self.get_workflows(repo_path)

        nodes: list[Node] = []

        for workflow_path in workflow_files:
            try:
                with open(workflow_path, encoding="utf-8") as wf:
                    lines = wf.readlines()
            except OSError as error:
                logger.debug("Unable to read Jenkinsfile %s: %s", workflow_path, error)
                return NodeForest([])

            # Find matching lines.
            for line in lines:
                match = re.match(pattern, line)
                if not match:
                    continue
                nodes.append(analyse_bash_script(match[1], workflow_path, repo_path))

        # return call_graph
        return NodeForest(nodes)

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
