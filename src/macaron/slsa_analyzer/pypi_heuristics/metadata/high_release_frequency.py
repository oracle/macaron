# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Analyzer checks the frequent release heuristic."""

import logging
from datetime import datetime

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

    def analyze(self) -> tuple[RESULT, dict]:
        """Check whether the release frequency is high.

        Returns
        -------
            tuple[RESULT, Confidence | None]: Confidence and result.
        """
        version_to_releases: dict | None = self.api_client.get_releases()
        if version_to_releases is None:
            return RESULT.SKIP, {}
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
        frequency = days_sum // (releases_amount - 1)

        if frequency <= self.average_gap_threshold:
            return RESULT.FAIL, {"frequency": frequency}
        return RESULT.PASS, {"frequency": frequency}
