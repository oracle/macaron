# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module checks if a SLSA provenances conforms to a given policy."""


import logging

from macaron.policy_engine.policy import PolicyRuntimeError
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck, CheckResultType
from macaron.slsa_analyzer.checks.check_result import CheckResult
from macaron.slsa_analyzer.ci_service.base_ci_service import NoneCIService
from macaron.slsa_analyzer.provenance.loader import SLSAProvenanceError
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class PolicyCheck(BaseCheck):
    """This check compares a SLSA provenance with a given policy and checks whether they match."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_policy_check_1"
        description = "Check whether the SLSA provenance for the produced artifact conforms to the policy."
        depends_on: list[tuple[str, CheckResultType]] = [("mcn_provenance_level_three_1", CheckResultType.PASSED)]
        eval_reqs = [ReqName.POLICY]
        super().__init__(
            check_id=check_id,
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.FAILED,
        )

    def run_check(self, ctx: AnalyzeContext, check_result: CheckResult) -> CheckResultType:
        """Implement the check in this method.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.
        check_result : CheckResult
            The object containing result data of a check.

        Returns
        -------
        CheckResultType
            The result type of the check (e.g. PASSED).
        """
        policy = ctx.dynamic_data["policy"]
        if not policy:
            check_result["justification"].append("No policy defined for repository.")
            return CheckResultType.FAILED

        ci_services = ctx.dynamic_data["ci_services"]
        for ci_info in ci_services:
            ci_service = ci_info["service"]
            # Checking if a CI service is discovered for this repo.
            if isinstance(ci_service, NoneCIService):
                continue

            # Checking if we have found a SLSA provenance for the repo.
            if ctx.dynamic_data["is_inferred_prov"] or not ci_info["provenances"]:
                logger.info("Could not find SLSA provenances.")
                break

            for payload in ci_info["provenances"]:
                try:
                    logger.info("Validating the provenance against %s.", policy)

                    if policy.validate(payload):
                        check_result["justification"].append("Successfully verified the policy against provenance.")
                        return CheckResultType.PASSED

                except (SLSAProvenanceError, PolicyRuntimeError) as error:
                    logger.error(error)
                    check_result["justification"].append("Could not verify policy against the provenance.")
                    return CheckResultType.FAILED

        check_result["justification"].append("Could not verify policy against the provenance.")
        return CheckResultType.FAILED


registry.register(PolicyCheck())
