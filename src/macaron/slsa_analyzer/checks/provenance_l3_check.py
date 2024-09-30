# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements a check to verify a target repo has intoto provenance level 3."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName


class ProvenanceL3VerifiedFacts(CheckFacts):
    """The ORM mapping for justifications in provenance_l3 check."""

    __tablename__ = "_provenance_l3_check"

    # The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    __mapper_args__ = {
        "polymorphic_identity": "_provenance_l3_check",
    }


class ProvenanceL3Check(BaseCheck):
    """This Check checks whether the target repo has SLSA provenance level 3."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_provenance_level_three_1"
        description = "Check whether the target has SLSA provenance level 3."
        depends_on: list[tuple[str, CheckResultType]] = [("mcn_provenance_available_1", CheckResultType.PASSED)]

        # SLSA 3: only identifies the top-level build config and not all the build inputs (hermetic).
        # TODO: revisit if ReqName.PROV_CONT_SOURCE should be here or not. That's because the definition
        # of source is not clear. See https://github.com/slsa-framework/slsa/issues/465.
        eval_reqs = [
            ReqName.PROV_NON_FALSIFIABLE,
            ReqName.PROV_CONT_BUILD_PARAMS,
            ReqName.PROV_CONT_ENTRY,
            ReqName.PROV_CONT_SOURCE,
        ]
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
        result_tables: list[CheckFacts] = []
        result_value = CheckResultType.FAILED
        if ctx.dynamic_data["provenance_l3_verified"]:
            result_tables.append(ProvenanceL3VerifiedFacts(confidence=Confidence.HIGH))
            result_value = CheckResultType.PASSED

        return CheckResultData(result_tables=result_tables, result_type=result_value)


registry.register(ProvenanceL3Check())
