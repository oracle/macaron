# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.


"""Analyzer checks the packages contain one release."""

from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import HeuristicResult
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseHeuristicAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC


class OneReleaseAnalyzer(BaseHeuristicAnalyzer):
    """Analyzer checks heuristic."""

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(name="one_release_analyzer", heuristic=HEURISTIC.ONE_RELEASE, depends_on=None)
        self.api_client = api_client

    def analyze(self) -> tuple[HeuristicResult, dict]:
        """Check the releases' total is one.

        Returns
        -------
            tuple[HeuristicResult, dict]: Result and confidence.
        """
        releases: dict | None = self.api_client.get_releases()
        if releases is None:
            return HeuristicResult.SKIP, {"releases": {}}

        if len(releases) == 1:
            return HeuristicResult.FAIL, {"releases": releases}  # Higher false positive, so we keep it MEDIUM
        return HeuristicResult.PASS, {"releases": releases}
