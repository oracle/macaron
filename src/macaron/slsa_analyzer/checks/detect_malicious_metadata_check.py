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

SUSPICIOUS_COMBO = {
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

    def _should_skip(self, results: dict, dependency_heuristic: tuple[HEURISTIC, RESULT]) -> bool:
        if results.get(dependency_heuristic[0], None) is not dependency_heuristic[1]:
            return True
        return False

    def _analyze(self, api_client: PyPIApiClient) -> dict:
        results: dict = {}
        detail_infos = {}
        for _analyzer in ANALYZERS:
            analyzer = _analyzer(api_client)
            depends_on = analyzer.depends_on

            skip_analyzer = False
            if depends_on:
                for heuristic in depends_on:  # e.g. heuristic = (HEURISTIC.ONE_RELEASE, RESULT.PASS)
                    if self._should_skip(results, heuristic):
                        skip_analyzer = True
                        break
            if skip_analyzer:
                continue
            result, detail_info = analyzer.analyze()
            if analyzer.heuristic:
                # logger.info(f"{analyzer.heuristic}:  {detail_info}")
                results[analyzer.heuristic] = result
                detail_infos.update(detail_info)

        results = {heuristic.value: result.value for heuristic, result in results.items()}
        results["detail_infos"] = detail_infos  # Package metadata
        return results

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
        result: dict = self._analyze(api_client)
        detail_infos = result.get("detail_infos", {})
        result.pop("detail_infos")
        heuristics_fail = [heuristic for heuristic, result in result.items() if result == "FAIL"]
        confidence = SUSPICIOUS_COMBO.get(tuple(result.values()), None)
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
