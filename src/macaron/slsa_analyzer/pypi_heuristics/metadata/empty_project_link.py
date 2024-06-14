# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Analyzer checks there is no project link of the package."""

from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIRegistry
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import HeuristicResult
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseHeuristicAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC


class EmptyProjectLinkAnalyzer(BaseHeuristicAnalyzer):
    """Analyzer checks heuristic."""

    def __init__(self) -> None:
        super().__init__(name="empty_project_link_analyzer", heuristic=HEURISTIC.EMPTY_PROJECT_LINK, depends_on=None)

    def analyze(self, api_client: PyPIRegistry) -> tuple[HeuristicResult, dict]:
        """Check whether the PyPI package has no project link.

        Returns
        -------
            tuple[HeuristicResult, dict]: Result and project links if they exist. Otherwise, return an empty dictionary
        """
        project_links: dict[str, str] | None = api_client.get_project_links()

        if project_links is None:
            return HeuristicResult.SKIP, {}

        if len(project_links) == 0:  # total
            return HeuristicResult.FAIL, {}
        return HeuristicResult.PASS, project_links
