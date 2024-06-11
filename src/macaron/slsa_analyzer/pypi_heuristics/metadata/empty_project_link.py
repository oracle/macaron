# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Analyzer checks there is no project link of the package."""

from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import RESULT
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC


class EmptyProjectLinkAnalyzer(BaseAnalyzer):
    """Analyzer checks heuristic."""

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(name="empty_project_link_analyzer", heuristic=HEURISTIC.EMPTY_PROJECT_LINK)
        self.api_client = api_client

    def _get_links_total(self) -> tuple[int, dict] | None:
        """Get total number of links.

        Returns
        -------
            int | None: Total number of links.
        """
        project_links: dict | None = self.api_client.get_project_links()
        if project_links is None:
            return None
        return len(project_links), project_links

    def analyze(self) -> tuple[RESULT, dict]:
        """Check whether the PyPI package has no project link.

        Returns
        -------
            tuple[RESULT, dict]: Result and confidence.
        """
        result: tuple[int, dict] | None = self._get_links_total()

        if result is None:
            return RESULT.SKIP, {}

        if result[0] == 0:  # total
            return RESULT.FAIL, {}
        return RESULT.PASS, result[1]
