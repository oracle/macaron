# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Heuristic analyzer to check unchanged content in multiple releases."""
import logging
from collections import Counter

from macaron.json_tools import json_extract
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIRegistry
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import HeuristicResult
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseHeuristicAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC

logger: logging.Logger = logging.getLogger(__name__)


class UnchangedReleaseAnalyzer(BaseHeuristicAnalyzer):
    """Analyzer checks heuristic."""

    def __init__(self) -> None:
        super().__init__(
            name="unchanged_release_analyzer",
            heuristic=HEURISTIC.UNCHANGED_RELEASE,
            depends_on=[(HEURISTIC.HIGH_RELEASE_FREQUENCY, HeuristicResult.FAIL)],  # Analyzing when this heuristic fail
        )
        self.hash_algo: str = "sha256"

    def _get_digests(self, api_client: PyPIRegistry) -> list[str] | None:
        """Get all digests of the releases.

        Returns
        -------
            list | None: Digests.
        """
        releases: dict | None = api_client.get_releases()
        if releases is None:
            return None

        digests: list[str] = []
        for _, metadata in releases.items():
            if metadata:
                digest: str | None = json_extract(metadata[0], ["digests", self.hash_algo], str)
                if digest is None:
                    continue
                digests.append(digest)

        return digests

    def analyze(self, api_client: PyPIRegistry) -> tuple[HeuristicResult, dict]:
        """Check the content of releases keep updating.

        Returns
        -------
            tuple[HeuristicResult, Confidence | None]: Result and confidence.
        """
        digests: list[str] | None = self._get_digests(api_client)
        if digests is None:
            return HeuristicResult.SKIP, {}

        frequency = Counter(digests)
        highest_frequency = max(frequency.values())
        if highest_frequency > 1:  # Any two release are same
            return HeuristicResult.FAIL, {}
        return HeuristicResult.PASS, {}
