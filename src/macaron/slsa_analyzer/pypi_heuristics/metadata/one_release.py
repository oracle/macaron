# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.


"""Analyzer checks the packages contain one release."""

from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import RESULT
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC


class OneReleaseAnalyzer(BaseAnalyzer):
    """Analyzer checks heuristic."""

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(name="one_release_analyzer", heuristic=HEURISTIC.ONE_RELEASE)
        self.api_client = api_client

    def _get_releases_total(self) -> tuple[int, dict] | None:
        """Get total releases number.

        Returns
        -------
            tuple[int, dict] | None: Releases' total.
        """
        releases: dict | None = self.api_client.get_releases()
        if releases:
            return len(releases), releases
        return None

    def analyze(self) -> tuple[RESULT, dict]:
        """Check the releases' total is one.

        Returns
        -------
            tuple[RESULT, dict]: Result and confidence.
        """
        result: tuple[int, dict] | None = self._get_releases_total()
        if result is None:
            return RESULT.SKIP, {"releases": {}}

        if result[0] == 1:
            return RESULT.FAIL, {"releases": result[1]}  # Higher false positive, so we keep it MEDIUM
        return RESULT.PASS, {"releases": result[1]}
