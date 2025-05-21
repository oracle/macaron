# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This check examines the metadata of pypi packages with seven heuristics."""

import logging

from problog import get_evaluatable
from problog.logic import Term
from problog.program import PrologString
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.db_custom_types import DBJsonDict
from macaron.database.table_definitions import CheckFacts
from macaron.errors import HeuristicAnalyzerValueError
from macaron.json_tools import JsonType, json_extract
from macaron.malware_analyzer.pypi_heuristics.base_analyzer import BaseHeuristicAnalyzer
from macaron.malware_analyzer.pypi_heuristics.heuristics import HeuristicResult, Heuristics
from macaron.malware_analyzer.pypi_heuristics.metadata.anomalous_version import AnomalousVersionAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.closer_release_join_date import CloserReleaseJoinDateAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.empty_project_link import EmptyProjectLinkAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.high_release_frequency import HighReleaseFrequencyAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.one_release import OneReleaseAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.source_code_repo import SourceCodeRepoAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.unchanged_release import UnchangedReleaseAnalyzer
from macaron.malware_analyzer.pypi_heuristics.metadata.wheel_absence import WheelAbsenceAnalyzer
from macaron.malware_analyzer.pypi_heuristics.pypi_sourcecode_analyzer import PyPISourcecodeAnalyzer
from macaron.malware_analyzer.pypi_heuristics.sourcecode.suspicious_setup import SuspiciousSetupAnalyzer
from macaron.malware_analyzer.pypi_heuristics.sourcecode.white_spaces import WhiteSpacesAnalyzer
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.package_registry.deps_dev import APIAccessError, DepsDevService
from macaron.slsa_analyzer.package_registry.osv_dev import OSVDevService
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIPackageJsonAsset, PyPIRegistry
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


class MaliciousMetadataFacts(CheckFacts):
    """The ORM mapping for justifications in malicious metadata check."""

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


class DetectMaliciousMetadataCheck(BaseCheck):
    """This check analyzes the metadata of a package for malicious behavior."""

    def __init__(self) -> None:
        """Initialize a check instance."""
        check_id = "mcn_detect_malicious_metadata_1"
        description = """This check analyzes the metadata of a package based on reports malicious behavior.
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

    def validate_malware(self, pypi_package_json: PyPIPackageJsonAsset) -> tuple[bool, dict[str, JsonType] | None]:
        """Validate the package is malicious.

        Parameters
        ----------
        pypi_package_json: PyPIPackageJsonAsset

        Returns
        -------
        tuple[bool, dict[str, JsonType] | None]
            Returns True if the source code includes suspicious pattern.
            Returns the result of the validation including the line number
            and the suspicious arguments.
            e.g. requests.get("http://malicious.com")
            return the "http://malicious.com"
        """
        # TODO: This redundant function might be removed
        sourcecode_analyzer = PyPISourcecodeAnalyzer(pypi_package_json)
        is_malware, detail_info = sourcecode_analyzer.analyze()
        return is_malware, detail_info

    def evaluate_heuristic_results(
        self, heuristic_results: dict[Heuristics, HeuristicResult]
    ) -> tuple[float, JsonType]:
        """Analyse the heuristic results to determine the maliciousness of the package.

        Parameters
        ----------
        heuristic_results: dict[Heuristics, HeuristicResult]
            Dictionary of Heuristic keys with HeuristicResult values, results of each heuristic scan.

        Returns
        -------
        tuple[float, JsonType]
            Returns the confidence associated with the detected malicious combination, and associated rule IDs detailing
            what rules were triggered and their confidence as a dict[str, float] type.
        """
        facts_list: list[str] = []
        triggered_rules: dict[str, JsonType] = {}

        for heuristic, result in heuristic_results.items():
            if result == HeuristicResult.PASS:
                facts_list.append(f"{heuristic.value} :- true.")
            elif result == HeuristicResult.FAIL:
                facts_list.append(f"{heuristic.value} :- false.")
            # Do not define for HeuristicResult.SKIP

        facts = "\n".join(facts_list)
        problog_code = f"{facts}\n\n{self.malware_rules_problog_model}"
        logger.debug("Problog model used for evaluation:\n %s", problog_code)

        problog_model = PrologString(problog_code)
        problog_results: dict[Term, float] = get_evaluatable().create_from(problog_model).evaluate()

        confidence = problog_results.pop(Term(self.problog_result_access), 0.0)
        if confidence > 0:  # a rule was triggered
            for term, conf in problog_results.items():
                if term.args:
                    triggered_rules[str(term.args[0])] = conf

        return confidence, triggered_rules

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

        for _analyzer in self.analyzers:
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
        package_registry_info_entries = ctx.dynamic_data["package_registries"]

        # First check if this package is a known malware
        package_exists = False
        try:
            package_exists = bool(DepsDevService.get_package_info(ctx.component.purl))
        except APIAccessError as error:
            logger.debug(error)

        # Known malicious packages must have been removed.
        if not package_exists:
            vulns: list = []
            try:
                vulns = OSVDevService.get_vulnerabilities_purl(ctx.component.purl)
            except APIAccessError as error:
                logger.debug(error)

            for vuln in vulns:
                if v_id := json_extract(vuln, ["id"], str):
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

        # If the package is not a known malware, run malware analysis heuristics.
        for package_registry_info_entry in package_registry_info_entries:
            match package_registry_info_entry:
                # Currently, only PyPI packages are supported.
                case PackageRegistryInfo(
                    build_tool_name="pip" | "poetry",
                    build_tool_purl_type="pypi",
                    package_registry=PyPIRegistry() as pypi_registry,
                ) as pypi_registry_info:
                    # Retrieve the pre-existing AssetLocator object for the PyPI package JSON object, if it exists.
                    pypi_package_json = next(
                        (
                            asset
                            for asset in pypi_registry_info.metadata
                            if isinstance(asset, PyPIPackageJsonAsset)
                            and asset.component_name == ctx.component.name
                            and asset.component_version == ctx.component.version
                        ),
                        None,
                    )
                    if not pypi_package_json:
                        # Create an AssetLocator object for the PyPI package JSON object.
                        pypi_package_json = PyPIPackageJsonAsset(
                            component_name=ctx.component.name,
                            component_version=ctx.component.version,
                            has_repository=ctx.component.repository is not None,
                            pypi_registry=pypi_registry,
                            package_json={},
                        )

                    pypi_registry_info.metadata.append(pypi_package_json)

                    # Download the PyPI package JSON, but no need to persist it to the filesystem.
                    if pypi_package_json.package_json or pypi_package_json.download(dest=""):
                        try:
                            result, detail_info = self.run_heuristics(pypi_package_json)
                        except HeuristicAnalyzerValueError:
                            return CheckResultData(result_tables=[], result_type=CheckResultType.UNKNOWN)

                        confidence, triggered_rules = self.evaluate_heuristic_results(result)
                        detail_info["triggered_rules"] = triggered_rules
                        result_type = CheckResultType.FAILED
                        if not confidence:
                            confidence = Confidence.HIGH
                            result_type = CheckResultType.PASSED
                        elif ctx.dynamic_data["validate_malware"]:
                            is_malware, validation_result = self.validate_malware(pypi_package_json)
                            if is_malware:  # Find source code block matched the malicious pattern
                                confidence = Confidence.HIGH
                            elif validation_result:  # Find suspicious source code, but cannot be confirmed
                                confidence = Confidence.MEDIUM
                            logger.debug(validation_result)

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

    # This list contains the heuristic analyzer classes
    # When implementing new analyzer, appending the classes to this list
    analyzers: list = [
        EmptyProjectLinkAnalyzer,
        SourceCodeRepoAnalyzer,
        OneReleaseAnalyzer,
        HighReleaseFrequencyAnalyzer,
        UnchangedReleaseAnalyzer,
        CloserReleaseJoinDateAnalyzer,
        SuspiciousSetupAnalyzer,
        WheelAbsenceAnalyzer,
        AnomalousVersionAnalyzer,
        WhiteSpacesAnalyzer,
    ]

    # name used to query the result of all problog rules, so it can be accessed outside the model.
    problog_result_access = "result"

    malware_rules_problog_model = f"""
    % ----- Wrappers ------
    % When a heuristic is skipped, it is ommitted from the problog model facts definition. This means that references in this
    % static model must account for when they are not existent. These wrappers perform this function using the inbuilt try_call
    % problog function. It will try to evaluate the provided logic, and return false if it encounters an error, such as the fact
    % not being defined. For example, you are expecting A to pass, so we do:
    %
    % passed(A)
    %
    % If A was 'true', then this will return true, as A did pass. If A was 'false', then this will return false, as A did not pass.
    % If A was not defined, then this will return false, as A did not pass.
    % Please use these wrappers throughout the problog model for logic definitions.

    passed(H) :- try_call(H).
    failed(H) :- try_call(not H).

    % ----- Heuristic groupings -----
    % These are common combinations of heuristics that are used in many of the rules, thus themselves representing
    % certain behaviors. When changing or adding rules here, if there are frequent combinations of particular
    % heuristics, group them together here.

    % Maintainer has recently joined, publishing an undetailed page with no links.
    quickUndetailed :- failed({Heuristics.EMPTY_PROJECT_LINK.value}), failed({Heuristics.CLOSER_RELEASE_JOIN_DATE.value}).

    % Maintainer releases a suspicious setup.py and forces it to run by omitting a .whl file.
    forceSetup :- failed({Heuristics.SUSPICIOUS_SETUP.value}), failed({Heuristics.WHEEL_ABSENCE.value}).

    % ----- Suspicious Combinations -----

    % Package released recently with little detail, forcing the setup.py to run.
    {Confidence.HIGH.value}::trigger(malware_high_confidence_1) :-
        quickUndetailed, forceSetup, failed({Heuristics.ONE_RELEASE.value}).
    {Confidence.HIGH.value}::trigger(malware_high_confidence_2) :-
        quickUndetailed, forceSetup, failed({Heuristics.HIGH_RELEASE_FREQUENCY.value}).

    % Package released recently with little detail, with some more refined trust markers introduced: project links,
    % multiple different releases, but there is no source code repository matching it and the setup is suspicious.
    {Confidence.HIGH.value}::trigger(malware_high_confidence_3) :-
        failed({Heuristics.SOURCE_CODE_REPO.value}),
        failed({Heuristics.HIGH_RELEASE_FREQUENCY.value}),
        passed({Heuristics.UNCHANGED_RELEASE.value}),
        failed({Heuristics.CLOSER_RELEASE_JOIN_DATE.value}),
        forceSetup.

    % Package released with excessive whitespace in the code .
    {Confidence.HIGH.value}::trigger(malware_high_confidence_4) :-
        quickUndetailed, forceSetup, failed({Heuristics.WHITE_SPACES.value}).

    % Package released recently with little detail, with multiple releases as a trust marker, but frequent and with
    % the same code.
    {Confidence.MEDIUM.value}::trigger(malware_medium_confidence_1) :-
        quickUndetailed,
        failed({Heuristics.HIGH_RELEASE_FREQUENCY.value}),
        failed({Heuristics.UNCHANGED_RELEASE.value}),
        passed({Heuristics.SUSPICIOUS_SETUP.value}).

    % Package released recently with little detail and an anomalous version number for a single-release package.
    {Confidence.MEDIUM.value}::trigger(malware_medium_confidence_2) :-
        quickUndetailed,
        failed({Heuristics.ONE_RELEASE.value}),
        failed({Heuristics.ANOMALOUS_VERSION.value}).

    % ----- Evaluation -----

    % Aggregate result
    {problog_result_access} :- trigger(malware_high_confidence_1).
    {problog_result_access} :- trigger(malware_high_confidence_2).
    {problog_result_access} :- trigger(malware_high_confidence_3).
    {problog_result_access} :- trigger(malware_high_confidence_4).
    {problog_result_access} :- trigger(malware_medium_confidence_2).
    {problog_result_access} :- trigger(malware_medium_confidence_1).
    query({problog_result_access}).

    % Explainability
    query(trigger(_)).
    """


registry.register(DetectMaliciousMetadataCheck())
