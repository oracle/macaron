# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The heuristic analyzer to check the project links."""

import logging

import requests

from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import HeuristicResult
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC

logger: logging.Logger = logging.getLogger(__name__)


class UnreachableProjectLinksAnalyzer(BaseAnalyzer):
    """If >= 1 project links are reachable, the analyzer consider the package as benign."""

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(
            name="unreachable_project_links_analyzer",
            heuristic=HEURISTIC.UNREACHABLE_PROJECT_LINKS,
            depends_on=[(HEURISTIC.EMPTY_PROJECT_LINK, HeuristicResult.PASS)],  # Analyzing when this heuristic pass
        )
        self.api_client = api_client

    def analyze(self) -> tuple[HeuristicResult, dict]:
        """Analyze the package.

        Returns
        -------
            tuple[HeuristicResult, Confidence | None]: Result type and confidence type.
        """
        project_links: dict | None = self.api_client.get_project_links()

        if project_links is None:
            return HeuristicResult.SKIP, {}

        for link in project_links.values():
            try:
                response = requests.head(link, timeout=3)
                if response.status_code < 400:
                    return HeuristicResult.PASS, {"project_links": project_links}
            except requests.exceptions.RequestException as error:
                logger.debug(error)
                continue
        return HeuristicResult.FAIL, {}
