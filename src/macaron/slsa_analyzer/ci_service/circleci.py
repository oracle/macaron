# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module analyze Circle CI."""

from typing import Iterable

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.config.defaults import defaults
from macaron.parsers.bashparser import BashCommands
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService


class CircleCI(BaseCIService):
    """This class implements CircleCI service."""

    def __init__(self) -> None:
        super().__init__(name="circle_ci")
        self.entry_conf = [".circleci/config.yml"]

    def get_workflows(self, repo_path: str) -> list:
        return []

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        if "ci.circle_ci" in defaults:
            for item in defaults["ci.circle_ci"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("ci.circle_ci", item))

    def set_api_client(self) -> None:
        pass

    def build_call_graph(self, repo_path: str, macaron_path: str = None) -> CallGraph:
        return CallGraph(BaseNode(), "")

    def extract_all_bash(self, callgraph: CallGraph, macaron_path: str = None) -> Iterable[BashCommands]:
        return []

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        return ""
