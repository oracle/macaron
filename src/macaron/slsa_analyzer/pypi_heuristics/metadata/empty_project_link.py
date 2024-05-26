# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Analyzer checks there is no project link of the package."""

from macaron.slsa_analyzer.checks.check_result import Confidence
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import RESULT
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC


class EmptyProjectLinkAnalyzer(BaseAnalyzer):
    """Analyzer checks heuristic."""

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(name="empty_project_link_analyzer", heuristic=HEURISTIC.EMPTY_PROJECT_LINK)
        self.api_client = api_client

    def _get_links_total(self) -> int | None:
        """Get total number of links.

        Returns
        -------
            int | None: Total number of links.
        """
        project_links: dict | None = self.api_client.get_project_links()
        if project_links is None:
            return 0
        return len(project_links)

    def analyze(self) -> tuple[RESULT, Confidence | None]:
        """Check whether the package contains one link.

        Returns
        -------
            tuple[RESULT, Confidence | None]: Result and confidence.
        """
        links_total: int | None = self._get_links_total()

        if links_total is None:
            return RESULT.SKIP, None

        if links_total == 0:
            return RESULT.FAIL, Confidence.LOW
        return RESULT.PASS, Confidence.HIGH
