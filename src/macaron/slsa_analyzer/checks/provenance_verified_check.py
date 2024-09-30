# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module adds a Check that checks whether the provenance is verified."""
import logging

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.json_tools import json_extract
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class ProvenanceVerifiedFacts(CheckFacts):
    """The ORM mapping for justifications in the provenance verified check."""

    __tablename__ = "_provenance_verified_check"

    # The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    # The SLSA build level of the provenance.
    build_level: Mapped[int]

    # The build type of the provenance.
    build_type: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.TEXT})

    __mapper_args__ = {
        "polymorphic_identity": __tablename__,
    }


class ProvenanceVerifiedCheck(BaseCheck):
    """This Check checks whether the provenance is flagged as verified in the context."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_provenance_verified_1"
        description = "Check whether the provenance is verified."
        depends_on: list[tuple[str, CheckResultType]] = []
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
        if ctx.dynamic_data["is_inferred_prov"] or not ctx.dynamic_data["provenance"]:
            # 0. Provenance is not available.
            return CheckResultData(
                result_tables=[ProvenanceVerifiedFacts(build_level=0, confidence=Confidence.HIGH)],
                result_type=CheckResultType.FAILED,
            )

        predicate = ctx.dynamic_data["provenance"].statement.get("predicate")
        build_type = None
        if predicate:
            build_type = json_extract(predicate, ["buildType"], str)

        if (
            build_type == "https://github.com/slsa-framework/slsa-github-generator/generic@v1"
            and ctx.dynamic_data["provenance_l3_verified"]
        ):
            # 3. Provenance is created by the SLSA GitHub generator and verified.
            return CheckResultData(
                result_tables=[
                    ProvenanceVerifiedFacts(build_level=3, build_type=build_type, confidence=Confidence.HIGH)
                ],
                result_type=CheckResultType.PASSED,
            )

        if ctx.dynamic_data["provenance_verified"]:
            # 2. Provenance is verified.
            return CheckResultData(
                result_tables=[
                    ProvenanceVerifiedFacts(
                        build_level=2,
                        build_type=build_type,
                        confidence=Confidence.HIGH,
                    )
                ],
                result_type=CheckResultType.PASSED,
            )

        # 1. Provenance is not verified.
        return CheckResultData(
            result_tables=[
                ProvenanceVerifiedFacts(
                    build_level=1,
                    build_type=build_type,
                    confidence=Confidence.HIGH,
                )
            ],
            result_type=CheckResultType.FAILED,
        )


registry.register(ProvenanceVerifiedCheck())
