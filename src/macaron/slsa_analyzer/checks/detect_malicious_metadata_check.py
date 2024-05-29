# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This check examines the metadata of pypi packages with seven heuristics."""

import logging

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import Analysis
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

    #: The provenance asset name.
    package_name: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    result: Mapped[dict] = mapped_column(JSON, nullable=False)

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


class DetectMaliciousMetadataCheck(BaseCheck):
    """This check analyzes the metadata of the PyPI package based on seven heuristics."""

    def __init__(self) -> None:
        """Initialize a check instance."""
        check_id = "mcn_pypi_package_heuristic_1"
        description = "Check whether the features of package adhere to the heurisic."
        super().__init__(
            check_id=check_id,
            description=description,
        )

    def _analyze(self, api_client: PyPIApiClient) -> dict:
        analysis = Analysis()
        results: dict = {}
        for _analyzer in ANALYZERS:
            analyzer = _analyzer(api_client)
            depends_on = analyzer.depends_on

            if depends_on and any(analysis.get_result(heuristic[0]) is not heuristic[1] for heuristic in depends_on):
                continue
            result, confidence = analyzer.analyze()
            if analyzer.heuristic:
                analysis.set_result(analyzer.heuristic, result)
                heuristic = analyzer.name[: -len("_analyzer")]
                results[heuristic] = (result.value, confidence)
        return results

    def _aggregate_confidence(self, confidences: list[Confidence]) -> Confidence:
        return confidences[0]

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
        dependencies = ["requests", "tqdm", "tttt1923"]
        # dependencies = ctx.component.dependencies
        results: list = []
        result_tables: list[CheckFacts] = []

        for pypi_package in dependencies:
            api_client = PyPIApiClient(pypi_package)
            result_and_confidence: dict = self._analyze(api_client)
            results.append(result_and_confidence)
            result_tables.append(
                HeuristicAnalysisResultFacts(
                    package_name=pypi_package, result=result_and_confidence, confidence=Confidence.LOW
                )
            )
        logger.info("[RESULT]  %s", results)
        # result_tables: list[CheckFacts] = [
        #         ProvenanceAvailableFacts(asset_name=asset.name, asset_url=asset.url, confidence=Confidence.HIGH)
        #         for asset in provenance_assets
        #     ]
        #     return CheckResultData(result_tables=result_tables, result_type=CheckResultType.PASSED)
        # if ctx.dynamic_data["provenance"]:
        #     return CheckResultData(
        #         result_tables=[ProvenanceAvailableFacts(confidence=Confidence.HIGH)],
        #         result_type=CheckResultType.PASSED,
        #     )

        return CheckResultData(
            result_tables=result_tables,
            result_type=CheckResultType.FAILED,
        )


registry.register(DetectMaliciousMetadataCheck())
