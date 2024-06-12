# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This check examines the metadata of pypi packages with seven heuristics."""

import logging

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import RESULT
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC
from macaron.slsa_analyzer.pypi_heuristics.metadata.closer_release_join_date import CloserReleaseJoinDateAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.metadata.empty_project_link import EmptyProjectLinkAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.metadata.high_release_frequency import HighReleaseFrequencyAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.metadata.one_release import OneReleaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.metadata.unchanged_release import UnchangedReleaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.metadata.unreachable_project_links import UnreachableProjectLinksAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.sourcecode.suspicious_setup import SuspiciousSetupAnalyzer
from macaron.slsa_analyzer.registry import registry

logger: logging.Logger = logging.getLogger(__name__)


class HeuristicAnalysisResultFacts(CheckFacts):
    """The ORM mapping for justifications in pypi heuristic check."""

    __tablename__ = "_detect_malicious_metadata_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: List of heuristic names that failed.
    heuristics_fail: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: Detailed information about the analysis.
    detail_information: Mapped[str] = mapped_column(
        String, nullable=False, info={"justification": JustificationType.TEXT}
    )

    #: The result of heuristic analysis.
    heuristic_result: Mapped[str] = mapped_column(
        String, nullable=False, info={"justification": JustificationType.TEXT}
    )

    __mapper_args__ = {
        "polymorphic_identity": "_detect_malicious_metadata_check",
    }


ANALYZERS = [
    EmptyProjectLinkAnalyzer,
    UnreachableProjectLinksAnalyzer,
    OneReleaseAnalyzer,
    HighReleaseFrequencyAnalyzer,
    UnchangedReleaseAnalyzer,
    CloserReleaseJoinDateAnalyzer,
    SuspiciousSetupAnalyzer,
]

SUSPICIOUS_COMBO: dict[tuple[RESULT, RESULT, RESULT, RESULT, RESULT, RESULT, RESULT], float] = {
    (RESULT.FAIL, RESULT.SKIP, RESULT.FAIL, RESULT.SKIP, RESULT.SKIP, RESULT.FAIL, RESULT.FAIL): Confidence.HIGH,
    (RESULT.FAIL, RESULT.SKIP, RESULT.FAIL, RESULT.SKIP, RESULT.SKIP, RESULT.FAIL, RESULT.PASS): Confidence.MEDIUM,
    (
        RESULT.FAIL,
        RESULT.SKIP,
        RESULT.PASS,
        RESULT.FAIL,
        RESULT.FAIL,
        RESULT.FAIL,
        RESULT.FAIL,
    ): Confidence.HIGH,  # The content changed and no-changed
    (
        RESULT.FAIL,
        RESULT.SKIP,
        RESULT.PASS,
        RESULT.FAIL,
        RESULT.PASS,
        RESULT.FAIL,
        RESULT.FAIL,
    ): Confidence.HIGH,  # The content changed and no-changed
    (
        RESULT.FAIL,
        RESULT.SKIP,
        RESULT.PASS,
        RESULT.FAIL,
        RESULT.FAIL,
        RESULT.FAIL,
        RESULT.PASS,
    ): Confidence.MEDIUM,  # The content changed and no-changed
    (
        RESULT.FAIL,
        RESULT.SKIP,
        RESULT.PASS,
        RESULT.FAIL,
        RESULT.PASS,
        RESULT.FAIL,
        RESULT.PASS,
    ): Confidence.MEDIUM,  # The content changed and no-changed
}


class DetectMaliciousMetadataCheck(BaseCheck):
    """This check analyzes the metadata of the package based on seven heuristics."""

    def __init__(self) -> None:
        """Initialize a check instance."""
        check_id = "mcn_detect_malicious_metadata_1"
        description = "Check whether the features of package adhere to the heurisic."
        super().__init__(
            check_id=check_id,
            description=description,
        )

    def _should_skip(self, results: dict[HEURISTIC, RESULT], depends_on: list[tuple[HEURISTIC, RESULT]]) -> bool:
        """Determine whether a particular heuristic result should be skipped based on the provided dependency heuristics.

        Args
        ----
            results (dict[HEURISTIC, RESULT]): Containing all heuristic results, where the key is the heuristic and the value
            is the result associated with that heuristic.
            depends_on (list[tuple[HEURISTIC, RESULT]]): containing heuristics that the current heuristic depends on,
            along with their expected results.

        Returns
        -------
            bool: Returns True if any result of the dependency heuristic does not match the expected result.
            Otherwise, returns False.
        """
        for heuristic, expected_result in depends_on:
            dep_heuristic_result: RESULT | None = results.get(heuristic, None)
            if dep_heuristic_result is not expected_result:
                return True
        return False

    def run_heuristics(self, api_client: PyPIApiClient) -> tuple[dict[HEURISTIC, RESULT], dict[str, int | dict]]:
        """Run the main logic of heuristics analysis.

        Args
        ----
            api_client (PyPIApiClient): The PyPI API client object used to interact with the official PyPI API.

        Returns
        -------
            tuple[dict[HEURISTIC, RESULT], dict[str, Any]]: Containing the heuristic results and relevant metadata.
        """
        results: dict[HEURISTIC, RESULT] = {}
        detail_infos: dict[str, int | dict] = {}
        for _analyzer in ANALYZERS:
            analyzer = _analyzer(api_client)
            depends_on = analyzer.depends_on

            if depends_on:
                should_skip: bool = self._should_skip(results, depends_on)
                if should_skip and isinstance(analyzer.heuristic, HEURISTIC):
                    results[analyzer.heuristic] = RESULT.SKIP
                    continue
            result, detail_info = analyzer.analyze()
            if analyzer.heuristic:
                # logger.info(f"{analyzer.heuristic}:  {detail_info}")
                results[analyzer.heuristic] = result
                detail_infos.update(detail_info)

        return results, detail_info

    def run_check(self, ctx: AnalyzeContext) -> CheckResultData:
        """Implement the check in this method.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.

        Returns
        -------
        CheckResultData
            The result of the check.
        """
        package = "requests"
        result_tables: list[CheckFacts] = []

        api_client = PyPIApiClient(package)
        result, detail_infos = self.run_heuristics(api_client)
        heuristics_fail = [heuristic.value for heuristic, result in result.items() if result is RESULT.FAIL]
        result_combo: tuple = tuple(result.values())
        confidence = SUSPICIOUS_COMBO.get(result_combo, None)
        result_type = CheckResultType.FAILED
        if confidence is None:
            confidence = Confidence.HIGH
            result_type = CheckResultType.PASSED

        result_tables.append(
            HeuristicAnalysisResultFacts(
                heuristics_fail=str(heuristics_fail),
                heuristic_result=str(result),
                detail_information=str(detail_infos),
                confidence=confidence,
            )
        )

        return CheckResultData(
            result_tables=result_tables,
            result_type=result_type,
        )


registry.register(DetectMaliciousMetadataCheck())
