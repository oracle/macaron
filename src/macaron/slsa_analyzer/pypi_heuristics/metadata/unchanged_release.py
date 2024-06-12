# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Heuristic analyzer to check unchanged content in multiple releases."""

from collections import Counter

from macaron.json_tools import json_extract
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import HeuristicResult
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseHeuristicAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC


class UnchangedReleaseAnalyzer(BaseHeuristicAnalyzer):
    """Analyzer checks heuristic."""

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(
            name="unchanged_release_analyzer",
            heuristic=HEURISTIC.UNCHANGED_RELEASE,
            depends_on=[(HEURISTIC.HIGH_RELEASE_FREQUENCY, HeuristicResult.FAIL)],  # Analyzing when this heuristic fail
        )
        self.hash_algo: str = "sha256"
        self.api_client = api_client

    def _get_digests(self) -> list[str] | None:
        """Get all digests of the releases.

        Returns
        -------
            list | None: Digests.
        """
        releases: dict | None = self.api_client.get_releases()
        if releases is None:
            return None

        digests: list[str] = []
        for _, metadata in releases.items():
            if metadata:
                _digests: dict | None = json_extract(metadata[0], ["digests"], dict)
                if _digests is None:
                    continue
                target_digest: str | None = json_extract(_digests, [self.hash_algo], str)
                if target_digest is None:
                    continue
                digests.append(target_digest)
        return digests

    def analyze(self) -> tuple[HeuristicResult, dict]:
        """Check the content of releases keep updating.

        Returns
        -------
            tuple[HeuristicResult, Confidence | None]: Result and confidence.
        """
        digests: list[str] | None = self._get_digests()
        if digests is None:
            return HeuristicResult.SKIP, {}

        frequency = Counter(digests)
        highest_frequency = max(frequency.values())
        if highest_frequency > 1:  # Any two release are same
            return HeuristicResult.FAIL, {}
        return HeuristicResult.PASS, {}
