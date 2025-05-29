# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the implementation of the Provenance Available check."""

import logging

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.database.table_definitions import CheckFacts
from macaron.errors import MacaronError
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class ProvenanceAvailableException(MacaronError):
    """When there is an error while checking if a provenance is available."""


class ProvenanceAvailableFacts(CheckFacts):
    """The ORM mapping for justifications in provenance_available check."""

    __tablename__ = "_provenance_available_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The provenance asset name.
    asset_name: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.TEXT})

    #: The URL for the provenance asset.
    asset_url: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

    __mapper_args__ = {
        "polymorphic_identity": "_provenance_available_check",
    }


class ProvenanceAvailableCheck(BaseCheck):
    """This Check checks whether the target repo has in-toto provenance."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_provenance_available_1"
        description = "Check whether the target has intoto provenance."
        depends_on: list[tuple[str, CheckResultType]] = []
        eval_reqs = [
            ReqName.PROV_AVAILABLE,
            ReqName.PROV_CONT_BUILD_INS,
            ReqName.PROV_CONT_ARTI,
            ReqName.PROV_CONT_BUILDER,
        ]
        super().__init__(check_id=check_id, description=description, depends_on=depends_on, eval_reqs=eval_reqs)

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
        provenance_info = None
        inferred = False
        if ctx.dynamic_data["provenance_info"]:
            provenance_info = ctx.dynamic_data["provenance_info"]
            inferred = ctx.dynamic_data["is_inferred_prov"]

        if not provenance_info or not provenance_info.provenance_payload or inferred:
            return CheckResultData(
                result_tables=[],
                result_type=CheckResultType.FAILED,
            )

        return CheckResultData(
            result_tables=[
                ProvenanceAvailableFacts(
                    confidence=Confidence.HIGH,
                    asset_name=provenance_info.provenance_asset_name,
                    asset_url=provenance_info.provenance_asset_url,
                )
            ],
            result_type=CheckResultType.PASSED,
        )


registry.register(ProvenanceAvailableCheck())
