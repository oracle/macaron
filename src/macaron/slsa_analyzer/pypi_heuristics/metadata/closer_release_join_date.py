# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Analyzer checks whether the maintainers' join date closer to latest package's release date."""

import logging
from datetime import datetime, timedelta

from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import RESULT
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC

logger: logging.Logger = logging.getLogger(__name__)


class CloserReleaseJoinDateAnalyzer(BaseAnalyzer):
    """Analyzer checks the heuristic.

    Note
    ----
        If any maintainer's date duration is larger than threshold,
        we consider it as "PASS".
    """

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(name="closer_release_join_date_analyzer", heuristic=HEURISTIC.CLOSER_RELEASE_JOIN_DATE)
        self.gap_threshold: int = 5
        self.api_client = api_client

    def _get_maintainers_join_date(self) -> list[datetime | None] | None:
        """Get the join date of the maintainers.

        Returns
        -------
            list[datetime] | None: Maintainers join date.

        Note
        ----
            Each package might have multiple maintainers.
        """
        maintainers: list | None = self.api_client.get_maintainer_of_package()
        if maintainers:
            join_date: list[datetime | None] = [
                self.api_client.get_maintainer_join_date(maintainer) for maintainer in maintainers
            ]
            return join_date
        return None

    def _get_latest_release_date(self) -> datetime | None:
        """Get package's latest release date.

        Returns
        -------
            datetime | None: Package's latest release date.
        """
        upload_time: str | None = self.api_client.get_latest_release_upload_time()
        if upload_time:
            return datetime.strptime(upload_time, "%Y-%m-%dT%H:%M:%S")
        return None

    def analyze(self) -> tuple[RESULT, dict]:
        """Check whether the maintainers' join date closer to package's latest release date.

        Returns
        -------
            tuple[RESULT, dict]: Result and confidence.
        """
        maintainers_join_date: list[datetime | None] | None = self._get_maintainers_join_date()
        latest_release_date: datetime | None = self._get_latest_release_date()
        detail_info = {
            "maintainers_join_date": [date.strftime("%Y-%m-%d %H:%M:%S") for date in maintainers_join_date if date]
            if maintainers_join_date
            else [],
            "latest_release_date": latest_release_date.strftime("%Y-%m-%d %H:%M:%S") if latest_release_date else "",
        }

        if maintainers_join_date is None or latest_release_date is None:
            return RESULT.SKIP, detail_info

        for date in maintainers_join_date:
            if date is None:
                continue
            difference = abs(latest_release_date - date)
            # Define a timedelta representing one day
            threshold_delta = timedelta(days=self.gap_threshold)

            if difference >= threshold_delta:
                return RESULT.PASS, detail_info
        return RESULT.FAIL, detail_info
