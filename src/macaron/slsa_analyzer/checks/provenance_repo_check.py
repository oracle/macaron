# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module adds a check that determines whether the repository URL came from provenance."""
import logging

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class ProvenanceDerivedRepoFacts(CheckFacts):
    """The ORM mapping for justifications in the repository from provenance check."""

    __tablename__ = "_provenance_derived_repo_check"

    # This check is disabled here due to a bug in pylint. The Mapped class triggers a false positive.
    # It may arbitrarily become true that this is no longer needed in this check, or will be needed in another check.
    # pylint: disable=unsubscriptable-object

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The state of the repository.
    repository_info: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.TEXT})

    __mapper_args__ = {
        "polymorphic_identity": __tablename__,
    }


class ProvenanceDerivedRepoCheck(BaseCheck):
    """This check tries to extract the repo from the provenance and compare it to what is in the context."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_provenance_derived_repo_1"
        description = "Check whether the repo came from provenance."
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
        if ctx.dynamic_data["provenance_info"] and ctx.dynamic_data["provenance_info"].repository_url:
            if not ctx.component.repository:
                return CheckResultData(
                    result_tables=[],
                    result_type=CheckResultType.FAILED,
                )

            current_repository = ctx.component.repository.remote_path

            if current_repository == ctx.dynamic_data["provenance_info"].repository_url:
                return CheckResultData(
                    result_tables=[
                        ProvenanceDerivedRepoFacts(
                            repository_info="The repository URL was found from provenance.", confidence=Confidence.HIGH
                        )
                    ],
                    result_type=CheckResultType.PASSED,
                )

        return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)


registry.register(ProvenanceDerivedRepoCheck())
