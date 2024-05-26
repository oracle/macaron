# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The heuristic analyzer to check the project links."""

import logging

import requests

from macaron.slsa_analyzer.checks.check_result import Confidence
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import RESULT
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC

logger: logging.Logger = logging.getLogger(__name__)


class UnreachableProjectLinksAnalyzer(BaseAnalyzer):
    """If >= 1 project links are reachable, the analyzer consider the package as benign."""

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(
            name="unreachable_project_links_analyzer",
            heuristic=HEURISTIC.UNREACHABLE_PROJECT_LINKS,
            depends_on=[(HEURISTIC.EMPTY_PROJECT_LINK, RESULT.PASS)],  # Analyzing when this heuristic pass
        )
        self.api_client = api_client

    def _get_project_links(self) -> dict | None:
        """Implement the method to get the project links.

        Returns
        -------
            dict | None: Link name to url.
        """
        project_links: dict | None = self.api_client.get_project_links()
        return project_links

    def analyze(self) -> tuple[RESULT, Confidence | None]:
        """Analyze the package.

        Returns
        -------
            tuple[RESULT, Confidence | None]: Result type and confidence type.
        """
        project_links: dict | None = self._get_project_links()

        if project_links is None:
            return RESULT.SKIP, None

        for link in project_links.values():
            try:
                response = requests.head(link, timeout=3)
                if response.status_code < 400:
                    return RESULT.PASS, Confidence.HIGH
            except requests.exceptions.RequestException as error:
                logger.debug(error)
                return RESULT.SKIP, None
        return RESULT.FAIL, Confidence.MEDIUM  # The source code might be moved to another repository
