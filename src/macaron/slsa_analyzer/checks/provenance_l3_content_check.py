# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module checks if a SLSA provenance conforms to a given expectation."""

import logging

from macaron.database.table_definitions import CheckFacts
from macaron.errors import ExpectationRuntimeError
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck, CheckResultType
from macaron.slsa_analyzer.checks.check_result import CheckResultData
from macaron.slsa_analyzer.ci_service.base_ci_service import NoneCIService
from macaron.slsa_analyzer.package_registry import JFrogMavenRegistry
from macaron.slsa_analyzer.provenance.loader import LoadIntotoAttestationError
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)

# Note: the ORM mappings for the results of this check are separately created per expectation
# object in the body of the check. There is no need to declare mappings explicitly again.


class ProvenanceL3ContentCheck(BaseCheck):
    """This check compares a SLSA provenance with a given expectation and checks whether they match."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_provenance_expectation_1"
        description = "Check whether the SLSA provenance for the produced artifact conforms to the expected value."
        depends_on: list[tuple[str, CheckResultType]] = [("mcn_provenance_available_1", CheckResultType.PASSED)]
        eval_reqs = [ReqName.EXPECTATION]
        super().__init__(
            check_id=check_id,
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.FAILED,
        )

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
        expectation = ctx.dynamic_data["expectation"]
        if not expectation:
            logger.info("%s check was unable to find any expectations.", self.check_info.check_id)
            return CheckResultData(result_tables=[], result_type=CheckResultType.UNKNOWN)

        if ctx.dynamic_data["provenance_info"] and ctx.dynamic_data["provenance_info"].provenance_payload:
            if expectation.validate(ctx.dynamic_data["provenance_info"].provenance_payload):
                return CheckResultData(
                    result_tables=[expectation],
                    result_type=CheckResultType.PASSED,
                )
            return CheckResultData(
                result_tables=[expectation],
                result_type=CheckResultType.FAILED,
            )

        package_registry_info_entries = ctx.dynamic_data["package_registries"]
        ci_services = ctx.dynamic_data["ci_services"]

        result_tables: list[CheckFacts] = []

        # Check the provenances in package registries.
        for package_registry_info_entry in package_registry_info_entries:
            match package_registry_info_entry:
                case PackageRegistryInfo(
                    package_registry=JFrogMavenRegistry(),
                ) as info_entry:
                    for provenance in info_entry.provenances:
                        try:
                            logger.info(
                                "Validating the provenance %s against %s.",
                                provenance.asset.url,
                                expectation,
                            )

                            if expectation.validate(provenance.payload):
                                expectation.asset_url = provenance.asset.url
                                result_tables.append(expectation)
                                return CheckResultData(
                                    result_tables=result_tables,
                                    result_type=CheckResultType.PASSED,
                                )

                        except (LoadIntotoAttestationError, ExpectationRuntimeError) as error:
                            logger.error(error)
                            return CheckResultData(
                                result_tables=result_tables,
                                result_type=CheckResultType.FAILED,
                            )

        for ci_info in ci_services:
            ci_service = ci_info["service"]
            # Checking if a CI service is discovered for this repo.
            if isinstance(ci_service, NoneCIService):
                continue

            # Checking if we have found a SLSA provenance for the repo.
            if ctx.dynamic_data["is_inferred_prov"] or not ci_info["provenances"]:
                logger.info("Could not find SLSA provenances.")
                break

            for provenance in ci_info["provenances"]:
                try:
                    logger.info("Validating a provenance from %s against %s.", ci_info["service"].name, expectation)

                    # TODO: Is it worth returning more information rather than returning early?
                    if expectation.validate(provenance.payload):
                        expectation.asset_url = provenance.asset.url
                        # We need to use typing.Protocol for multiple inheritance, however, the Expectation
                        # class uses inlined functions, which is not supported by Protocol.
                        result_tables.append(expectation)
                        return CheckResultData(result_tables=result_tables, result_type=CheckResultType.PASSED)

                except (LoadIntotoAttestationError, ExpectationRuntimeError) as error:
                    logger.error(error)
                    return CheckResultData(result_tables=result_tables, result_type=CheckResultType.FAILED)

        return CheckResultData(result_tables=result_tables, result_type=CheckResultType.FAILED)


registry.register(ProvenanceL3ContentCheck())
