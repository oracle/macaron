# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This file defines the heuristic-analysis result type enum, and function to modify result."""

from enum import Enum

from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC


class RESULT(Enum):
    """Result type.

    PASS: Not suspicious
    FAIL: Suspicious
    SKIP: Metadata miss
    """

    PASS = "PASS"  # nosec
    FAIL = "FAIL"  # nosec
    SKIP = "SKIP"  # nosec


class Analysis:
    """The heuristic result cache for each package or dependency."""

    def __init__(self) -> None:
        self.empty_project_link = RESULT.SKIP
        self.unreachable_project_links = RESULT.SKIP
        self.one_release = RESULT.SKIP
        self.high_release_frequency = RESULT.SKIP
        self.unchanged_release = RESULT.SKIP
        self.closer_release_join_date = RESULT.SKIP
        self.suspicious_setup = RESULT.SKIP

    def get_result(self, heuristic: HEURISTIC) -> RESULT:
        """Get the result in terms of the heuritic.

        Returns
        -------
            RESULT: Result type
        """
        match heuristic:
            case HEURISTIC.EMPTY_PROJECT_LINK:
                return self.empty_project_link
            case HEURISTIC.UNREACHABLE_PROJECT_LINKS:
                return self.unreachable_project_links
            case HEURISTIC.ONE_RELEASE:
                return self.one_release
            case HEURISTIC.HIGH_RELEASE_FREQUENCY:
                return self.high_release_frequency
            case HEURISTIC.UNCHANGED_RELEASE:
                return self.unchanged_release
            case HEURISTIC.CLOSER_RELEASE_JOIN_DATE:
                return self.closer_release_join_date
            case HEURISTIC.SUSPICIOUS_SETUP:
                return self.suspicious_setup

    def set_result(self, heuristic: HEURISTIC, result: RESULT) -> None:
        """Set the result.

        Parameters
        ----------
            heuristic (HEURISTIC): Heuristic type
            result (RESULT): The analysis result
        """
        match heuristic:
            case HEURISTIC.EMPTY_PROJECT_LINK:
                self.empty_project_link = result
            case HEURISTIC.UNREACHABLE_PROJECT_LINKS:
                self.unreachable_project_links = result
            case HEURISTIC.ONE_RELEASE:
                self.one_release = result
            case HEURISTIC.HIGH_RELEASE_FREQUENCY:
                self.high_release_frequency = result
            case HEURISTIC.UNCHANGED_RELEASE:
                self.unchanged_release = result
            case HEURISTIC.CLOSER_RELEASE_JOIN_DATE:
                self.closer_release_join_date = result
            case HEURISTIC.SUSPICIOUS_SETUP:
                self.suspicious_setup = result
            case _:
                pass
