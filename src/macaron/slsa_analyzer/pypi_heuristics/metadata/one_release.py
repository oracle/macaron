# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.


"""Analyzer checks the packages contain one release."""

from macaron.slsa_analyzer.checks.check_result import Confidence
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import RESULT
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC


class OneReleaseAnalyzer(BaseAnalyzer):
    """Analyzer checks heuristic."""

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(name="one_release_analyzer", heuristic=HEURISTIC.ONE_RELEASE)
        self.api_client = api_client

    def _get_releases_total(self) -> int | None:
        """Get total releases number.

        Returns
        -------
            int | None: Releases' total.
        """
        releases: dict | None = self.api_client.get_releases()
        return len(releases) if releases else None

    def analyze(self) -> tuple[RESULT, Confidence | None]:
        """Check the releases' total is one.

        Returns
        -------
            tuple[RESULT, Confidence | None]: Result and confidence.
        """
        releases_total: int | None = self._get_releases_total()
        if releases_total is None:
            return RESULT.SKIP, None

        if releases_total == 1:
            return RESULT.FAIL, Confidence.MEDIUM  # Higher false positive, so we keep it MEDIUM
        return RESULT.PASS, Confidence.MEDIUM
