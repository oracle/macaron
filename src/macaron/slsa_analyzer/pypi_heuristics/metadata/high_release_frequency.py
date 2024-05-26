# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Analyzer checks the frequent release heuristic."""

import logging
from datetime import datetime

from macaron.slsa_analyzer.checks.check_result import Confidence
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import RESULT
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC

logger: logging.Logger = logging.getLogger(__name__)


class HighReleaseFrequencyAnalyzer(BaseAnalyzer):
    """Analyzer checks heuristic."""

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(
            name="high_release_frequency_analyzer",
            heuristic=HEURISTIC.HIGH_RELEASE_FREQUENCY,
            depends_on=[(HEURISTIC.ONE_RELEASE, RESULT.PASS)],  # Analyzing when this heuristic pass
        )
        self.average_gap_threshold: int = 2  # Days
        self.api_client = api_client

    def _get_releases(self) -> dict | None:
        """Get all releases of the package.

        Returns
        -------
            dict | None: Version to metadata.
        """
        releases: dict | None = self.api_client.get_releases()
        return releases

    def analyze(self) -> tuple[RESULT, Confidence | None]:
        """Check whether the release frequency is high.

        Returns
        -------
            tuple[RESULT, Confidence | None]: Confidence and result.
        """
        version_to_releases: dict | None = self._get_releases()
        if version_to_releases is None:
            return RESULT.SKIP, None
        releases_amount = len(version_to_releases)
        extract_data: dict = {
            version: datetime.strptime(metadata[0].get("upload_time"), "%Y-%m-%dT%H:%M:%S")
            for version, metadata in version_to_releases.items()
            if metadata and "upload_time" in metadata[0]
        }
        prev_timestamp: str = next(iter(extract_data.values()))

        days_sum = 0
        releases = list(extract_data.values())[1:]
        for timestamp in releases:
            diff_timestamp = abs(timestamp - prev_timestamp)
            days_sum += diff_timestamp.days
        if days_sum // (releases_amount - 1) <= self.average_gap_threshold:
            return RESULT.FAIL, Confidence.LOW
        return RESULT.PASS, Confidence.HIGH
