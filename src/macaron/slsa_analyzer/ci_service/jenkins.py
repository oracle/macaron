# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module analyzes Jenkins CI."""

import glob
import logging
import os
import re
from collections.abc import Iterable
from enum import Enum
from typing import Any

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.errors import ParseError
from macaron.parsers import bashparser
from macaron.repo_verifier.repo_verifier import BaseBuildTool
from macaron.slsa_analyzer.build_tool.base_build_tool import BuildToolCommand
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
        if not macaron_path:
            macaron_path = global_config.macaron_path

        root: BaseNode = BaseNode()
        call_graph = CallGraph(root, repo_path)

        # To match lines that start with sh '' or sh ''' ''' (either single or triple quotes)
        # TODO: we need to support multi-line cases.
        pattern = r"^\s*sh\s+'{1,3}(.*?)'{1,3}$"
        workflow_files = self.get_workflows(repo_path)

        for workflow_path in workflow_files:
            try:
                with open(workflow_path, encoding="utf-8") as wf:
                    lines = wf.readlines()
            except OSError as error:
                logger.debug("Unable to read Jenkinsfile %s: %s", workflow_path, error)
                return call_graph

            # Add internal workflow.
            workflow_name = os.path.basename(workflow_path)
            workflow_node = JenkinsNode(
                name=workflow_name,
                node_type=JenkinsNodeType.INTERNAL,
                source_path=workflow_path,
                caller=root,
            )
            root.add_callee(workflow_node)

            # Find matching lines.
            for line in lines:
                match = re.match(pattern, line)
                if not match:
                    continue

                try:
                    parsed_bash_script = bashparser.parse(match.group(1), macaron_path=macaron_path)
                except ParseError as error:
                    logger.debug(error)
                    continue

                # TODO: Similar to GitHub Actions, we should enable support for recursive calls to bash scripts
                # within Jenkinsfiles. While the implementation should be relatively straightforward, it’s
                # recommended to first refactor the bashparser to make it agnostic to GitHub Actions.
                bash_node = bashparser.BashNode(
                    "jenkins_inline_cmd",
                    bashparser.BashScriptType.INLINE,
                    workflow_path,
                    parsed_step_obj=None,
                    parsed_bash_obj=parsed_bash_script,
                    node_id=None,
                    caller=workflow_node,
                )
                workflow_node.add_callee(bash_node)

        return call_graph

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
        yield from sorted(
            self._get_build_tool_commands(callgraph=callgraph, build_tool=build_tool),
            key=str,
        )

    def _get_build_tool_commands(self, callgraph: CallGraph, build_tool: BaseBuildTool) -> Iterable[BuildToolCommand]:
        """Traverse the callgraph and find all the reachable build tool commands."""
        for node in callgraph.bfs():
            # We are just interested in nodes that have bash commands.
            if isinstance(node, bashparser.BashNode):
                # The Jenkins configuration that triggers the path in the callgraph.
                workflow_node = node.caller

                # Find the bash commands that call the build tool.
                for cmd in node.parsed_bash_obj.get("commands", []):
                    if build_tool.is_build_command(cmd):
                        yield BuildToolCommand(
                            ci_path=workflow_node.source_path if workflow_node else "",
                            command=cmd,
                            step_node=None,
                            language=build_tool.language,
                            language_versions=None,
                            language_distributions=None,
                            language_url=None,
                            reachable_secrets=[],
                            events=None,
                        )

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


class JenkinsNodeType(str, Enum):
    """This class represents Jenkins node type."""

    INTERNAL = "internal"  # Configurations declared in one file.


class JenkinsNode(BaseNode):
    """This class represents a callgraph node for Jenkinsfile configuration."""

    def __init__(
        self,
        name: str,
        node_type: JenkinsNodeType,
        source_path: str,
        **kwargs: Any,
    ) -> None:
        """Initialize instance.

        Parameters
        ----------
        name : str
            Name of the workflow.
        node_type : JenkinsNodeType
            The type of node.
        source_path : str
            The path of the workflow.
        caller: BaseNode | None
            The caller node.
        """
        super().__init__(**kwargs)
        self.name = name
        self.node_type: JenkinsNodeType = node_type
        self.source_path = source_path

    def __str__(self) -> str:
        return f"JenkinsNodeType({self.name},{self.node_type})"
