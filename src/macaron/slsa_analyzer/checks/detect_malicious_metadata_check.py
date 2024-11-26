# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This check examines the metadata of pypi packages with seven heuristics."""

import logging

import requests
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.db_custom_types import DBJsonDict
from macaron.database.table_definitions import CheckFacts
from macaron.errors import HeuristicAnalyzerValueError
from macaron.json_tools import JsonType, json_extract
from macaron.malware_analyzer.pypi_heuristics.base_analyzer import BaseHeuristicAnalyzer
from macaron.malware_analyzer.pypi_heuristics.heuristics import HeuristicResult, Heuristics
from macaron.malware_analyzer.pypi_heuristics.metadata.closer_release_join_date import CloserReleaseJoinDateAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.empty_project_link import EmptyProjectLinkAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.high_release_frequency import HighReleaseFrequencyAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.one_release import OneReleaseAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.unchanged_release import UnchangedReleaseAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.unreachable_project_links import UnreachableProjectLinksAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.wheel_presence import WheelPresenceAnalyzer
from macaron.malware_analyzer.pypi_heuristics.sourcecode.suspicious_setup import SuspiciousSetupAnalyzer
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.pip import Pip
from macaron.slsa_analyzer.build_tool.poetry import Poetry
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIPackageJsonAsset, PyPIRegistry
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo
from macaron.util import send_post_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class MaliciousMetadataFacts(CheckFacts):
    """The ORM mapping for justifications in pypi heuristic check."""

    __tablename__ = "_detect_malicious_metadata_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: Known malware.
    known_malware: Mapped[str | None] = mapped_column(
        String, nullable=True, info={"justification": JustificationType.HREF}
    )

    #: Detailed information about the analysis.
    detail_information: Mapped[dict[str, JsonType]] = mapped_column(DBJsonDict, nullable=False)

    #: The result of analysis, which can be an empty dictionary.
    result: Mapped[dict[Heuristics, HeuristicResult]] = mapped_column(
        DBJsonDict, nullable=False, info={"justification": JustificationType.TEXT}
    )

    __mapper_args__ = {
        "polymorphic_identity": "_detect_malicious_metadata_check",
    }


# This list contains the heuristic analyzer classes
# When implementing new analyzer, appending the classes to this list
ANALYZERS: list = [
    EmptyProjectLinkAnalyzer,
    UnreachableProjectLinksAnalyzer,
    OneReleaseAnalyzer,
    HighReleaseFrequencyAnalyzer,
    UnchangedReleaseAnalyzer,
    CloserReleaseJoinDateAnalyzer,
    SuspiciousSetupAnalyzer,
    WheelPresenceAnalyzer,
]

# The HeuristicResult sequence is aligned with the sequence of ANALYZERS list
SUSPICIOUS_COMBO: dict[
    tuple[
        HeuristicResult,
        HeuristicResult,
        HeuristicResult,
        HeuristicResult,
        HeuristicResult,
        HeuristicResult,
        HeuristicResult,
        HeuristicResult,
    ],
    float,
] = {
    (
        HeuristicResult.FAIL,  # Empty Project
        HeuristicResult.SKIP,  # Unreachable Project Links
        HeuristicResult.FAIL,  # One Release
        HeuristicResult.SKIP,  # High Release Frequency
        HeuristicResult.SKIP,  # Unchanged Release
        HeuristicResult.FAIL,  # Closer Release Join Date
        HeuristicResult.FAIL,  # Suspicious Setup
        HeuristicResult.FAIL,  # Wheel Presence
        # No project link, only one release, and the maintainer released it shortly
        # after account registration.
        # The setup.py file contains suspicious imports and .whl file isn't present.
    ): Confidence.HIGH,
    (
        HeuristicResult.FAIL,  # Empty Project
        HeuristicResult.SKIP,  # Unreachable Project Links
        HeuristicResult.PASS,  # One Release
        HeuristicResult.FAIL,  # High Release Frequency
        HeuristicResult.FAIL,  # Unchanged Release
        HeuristicResult.FAIL,  # Closer Release Join Date
        HeuristicResult.FAIL,  # Suspicious Setup
        HeuristicResult.FAIL,  # Wheel Presence
        # No project link, frequent releases of multiple versions without modifying the content,
        # and the maintainer released it shortly after account registration.
        # The setup.py file contains suspicious imports and .whl file isn't present.
    ): Confidence.HIGH,
    (
        HeuristicResult.FAIL,  # Empty Project
        HeuristicResult.SKIP,  # Unreachable Project Links
        HeuristicResult.PASS,  # One Release
        HeuristicResult.FAIL,  # High Release Frequency
        HeuristicResult.PASS,  # Unchanged Release
        HeuristicResult.FAIL,  # Closer Release Join Date
        HeuristicResult.FAIL,  # Suspicious Setup
        HeuristicResult.FAIL,  # Wheel Presence
        # No project link, frequent releases of multiple versions,
        # and the maintainer released it shortly after account registration.
        # The setup.py file contains suspicious imports and .whl file isn't present.
    ): Confidence.HIGH,
    (
        HeuristicResult.FAIL,  # Empty Project
        HeuristicResult.SKIP,  # Unreachable Project Links
        HeuristicResult.PASS,  # One Release
        HeuristicResult.FAIL,  # High Release Frequency
        HeuristicResult.FAIL,  # Unchanged Release
        HeuristicResult.FAIL,  # Closer Release Join Date
        HeuristicResult.PASS,  # Suspicious Setup
        HeuristicResult.PASS,  # Wheel Presence
        # No project link, frequent releases of multiple versions without modifying the content,
        # and the maintainer released it shortly after account registration. Presence of .whl file
        # has no effect
    ): Confidence.MEDIUM,
    (
        HeuristicResult.FAIL,  # Empty Project
        HeuristicResult.SKIP,  # Unreachable Project Links
        HeuristicResult.PASS,  # One Release
        HeuristicResult.FAIL,  # High Release Frequency
        HeuristicResult.FAIL,  # Unchanged Release
        HeuristicResult.FAIL,  # Closer Release Join Date
        HeuristicResult.PASS,  # Suspicious Setup
        HeuristicResult.FAIL,  # Wheel Presence
        # No project link, frequent releases of multiple versions without modifying the content,
        # and the maintainer released it shortly after account registration. Presence of .whl file
        # has no effect
    ): Confidence.MEDIUM,
    (
        HeuristicResult.PASS,  # Empty Project
        HeuristicResult.FAIL,  # Unreachable Project Links
        HeuristicResult.PASS,  # One Release
        HeuristicResult.FAIL,  # High Release Frequency
        HeuristicResult.PASS,  # Unchanged Release
        HeuristicResult.FAIL,  # Closer Release Join Date
        HeuristicResult.FAIL,  # Suspicious Setup
        HeuristicResult.FAIL,  # Wheel Presence
        # All project links are unreachable, frequent releases of multiple versions,
        # and the maintainer released it shortly after account registration.
        # The setup.py file contains suspicious imports and .whl file isn't present.
    ): Confidence.HIGH,
}


class DetectMaliciousMetadataCheck(BaseCheck):
    """This check analyzes the metadata of a package for malicious behavior."""

    def __init__(self) -> None:
        """Initialize a check instance."""
        check_id = "mcn_detect_malicious_metadata_1"
        description = """This check analyzes the metadata of a package based on reports malicious behavior.
        Supported ecosystem: PyPI.
        """
        super().__init__(check_id=check_id, description=description, eval_reqs=[])

    def _should_skip(
        self, results: dict[Heuristics, HeuristicResult], depends_on: list[tuple[Heuristics, HeuristicResult]]
    ) -> bool:
        """Determine whether a particular heuristic result should be skipped based on the provided dependency heuristics.

        Parameters
        ----------
        results: dict[Heuristics, HeuristicResult]
            Containing all heuristics' results, where the key is the heuristic and the value is the result
            associated with that heuristic.
        depends_on: list[tuple[Heuristics, HeuristicResult]]
            Containing heuristics that the current heuristic depends on, along with their expected results.

        Returns
        -------
        bool
            Returns True if any result of the dependency heuristic does not match the expected result.
            Otherwise, returns False.
        """
        for heuristic, expected_result in depends_on:
            dep_heuristic_result: HeuristicResult = results[heuristic]
            if dep_heuristic_result is not expected_result:
                return True
        return False

    def run_heuristics(
        self, pypi_package_json: PyPIPackageJsonAsset
    ) -> tuple[dict[Heuristics, HeuristicResult], dict[str, JsonType]]:
        """Run the analysis heuristics.

        Parameters
        ----------
        pypi_package_json: PyPIPackageJsonAsset
            The PyPI package JSON asset object.

        Returns
        -------
        tuple[dict[Heuristics, HeuristicResult], dict[str, JsonType]]
            Containing the analysis results and relevant metadata.

        Raises
        ------
        HeuristicAnalyzerValueError
            If a heuristic analysis fails due to malformed package information.
        """
        results: dict[Heuristics, HeuristicResult] = {}
        detail_info: dict[str, JsonType] = {}
        for _analyzer in ANALYZERS:
            analyzer: BaseHeuristicAnalyzer = _analyzer()
            logger.debug("Instantiating %s", _analyzer.__name__)
            depends_on: list[tuple[Heuristics, HeuristicResult]] | None = analyzer.depends_on

            if depends_on:
                should_skip: bool = self._should_skip(results, depends_on)
                if should_skip:
                    results[analyzer.heuristic] = HeuristicResult.SKIP
                    continue

            result, result_info = analyzer.analyze(pypi_package_json)
            if analyzer.heuristic:
                results[analyzer.heuristic] = result
                detail_info.update(result_info)
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
        result_tables: list[CheckFacts] = []
        # First check if this package is a known malware

        url = "https://api.osv.dev/v1/query"
        data = {"package": {"purl": ctx.component.purl}}
        response = send_post_http_raw(url, json_data=data, headers=None)
        res_obj = None
        if response:
            try:
                res_obj = response.json()
            except requests.exceptions.JSONDecodeError as error:
                logger.debug("Unable to get a valid response from %s: %s", url, error)
        if res_obj:
            for vuln in res_obj.get("vulns", {}):
                v_id = json_extract(vuln, ["id"], str)
                if v_id and v_id.startswith("MAL-"):
                    result_tables.append(
                        MaliciousMetadataFacts(
                            known_malware=f"https://osv.dev/vulnerability/{v_id}",
                            result={},
                            detail_information=vuln,
                            confidence=Confidence.HIGH,
                        )
                    )
            if result_tables:
                return CheckResultData(
                    result_tables=result_tables,
                    result_type=CheckResultType.FAILED,
                )

        package_registry_info_entries = ctx.dynamic_data["package_registries"]
        for package_registry_info_entry in package_registry_info_entries:
            match package_registry_info_entry:
                case PackageRegistryInfo(
                    build_tool=Pip() | Poetry(),
                    package_registry=PyPIRegistry() as pypi_registry,
                ) as pypi_registry_info:

                    # Create an AssetLocator object for the PyPI package JSON object.
                    pypi_package_json = PyPIPackageJsonAsset(
                        component=ctx.component, pypi_registry=pypi_registry, package_json={}
                    )

                    pypi_registry_info.metadata.append(pypi_package_json)

                    # Download the PyPI package JSON, but no need to persist it to the filesystem.
                    if pypi_package_json.download(dest=""):
                        try:
                            result, detail_info = self.run_heuristics(pypi_package_json)
                        except HeuristicAnalyzerValueError:
                            return CheckResultData(result_tables=[], result_type=CheckResultType.UNKNOWN)

                        result_combo: tuple = tuple(result.values())
                        confidence: float | None = SUSPICIOUS_COMBO.get(result_combo, None)
                        result_type = CheckResultType.FAILED
                        if confidence is None:
                            confidence = Confidence.HIGH
                            result_type = CheckResultType.PASSED

                        result_tables.append(
                            MaliciousMetadataFacts(
                                result=result,
                                detail_information=detail_info,
                                confidence=confidence,
                            )
                        )

                        return CheckResultData(
                            result_tables=result_tables,
                            result_type=result_type,
                        )

        # Return UNKNOWN result for unsupported ecosystems.
        return CheckResultData(result_tables=[], result_type=CheckResultType.UNKNOWN)


registry.register(DetectMaliciousMetadataCheck())
