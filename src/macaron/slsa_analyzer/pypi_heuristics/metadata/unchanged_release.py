# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Heuristic analyzer to check unchanged content in multiple releases."""

from collections import Counter

from macaron.slsa_analyzer.checks.check_result import Confidence
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import RESULT
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC


class UnchangedReleaseAnalyzer(BaseAnalyzer):
    """Analyzer checks heuristic."""

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(
            name="unchanged_release_analyzer",
            heuristic=HEURISTIC.UNCHANGED_RELEASE,
            depends_on=[(HEURISTIC.HIGH_RELEASE_FREQUENCY, RESULT.FAIL)],  # Analyzing when this heuristic fail
        )
        self.hash: str = "sha256"
        self.api_client = api_client

    def _get_digests(self) -> list | None:
        """Get all digests of the releases.

        Returns
        -------
            list | None: Digests.
        """
        releases: dict | None = self.api_client.get_releases()
        if releases is None:
            return None
        digests: list = [
            metadata[0].get("digests").get(self.hash)
            for _, metadata in releases.items()
            if metadata and "digests" in metadata[0]
        ]
        return digests

    def analyze(self) -> tuple[RESULT, Confidence | None]:
        """Check the content of releases keep updating.

        Returns
        -------
            tuple[RESULT, Confidence | None]: Result and confidence.
        """
        digests: list | None = self._get_digests()
        if digests is None:
            return RESULT.SKIP, None

        frequency = Counter(digests)
        highest_frequency = max(frequency.values())
        if highest_frequency > 1:  # Any two release are same
            return RESULT.FAIL, Confidence.LOW
        return RESULT.PASS, Confidence.HIGH
