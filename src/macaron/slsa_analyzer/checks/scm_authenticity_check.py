# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""A check to determine whether the source repository of a package can be independently verified."""

import logging

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.repo_finder.repo_finder_deps_dev import DepsDevRepoFinder
from macaron.repo_verifier.repo_verifier_base import RepositoryVerificationStatus
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.registry import registry

logger: logging.Logger = logging.getLogger(__name__)


class ScmAuthenticityFacts(CheckFacts):
    """The ORM mapping for justifications in scm authenticity check."""

    __tablename__ = "_scm_authenticity_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: Repository link identified by Macaron's repo finder.
    repo_link: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

    #: Number of stars on the repository.
    stars_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, info={"justification": JustificationType.TEXT}
    )

    #: Number of forks on the repository.
    fork_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, info={"justification": JustificationType.TEXT}
    )

    #: The status of repo verification: passed, failed, or unknown.
    status: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The reason for the status.
    reason: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The build tool used to build the package.
    build_tool: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    __mapper_args__ = {
        "polymorphic_identity": __tablename__,
    }


class ScmAuthenticityCheck(BaseCheck):
    """Check whether the claims of a source repository provenance made by a package can be corroborated."""

    def __init__(self) -> None:
        """Initialize a check instance."""
        check_id = "mcn_scm_authenticity_1"
        description = (
            "Check whether the claims of a source repository provenance"
            " made by a package can be corroborated."
            " At this moment, this check only supports Maven packages"
            " and returns UNKNOWN for others."
        )

        super().__init__(
            check_id=check_id,
            description=description,
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
        # Only support Maven at the moment.
        # TODO: Add support for other systems.
        if ctx.component.type != "maven":
            return CheckResultData(result_tables=[], result_type=CheckResultType.UNKNOWN)

        stars_count: int | None = None
        fork_count: int | None = None
        deps_dev_repo_info: dict | None = None

        repo_link = ctx.component.repository.remote_path if ctx.component.repository else None
        if repo_link:
            deps_dev_repo_info = DepsDevRepoFinder.get_project_info(repo_link)

        if deps_dev_repo_info:
            stars_count = deps_dev_repo_info.get("starsCount")
            fork_count = deps_dev_repo_info.get("forksCount")

        result_type = CheckResultType.UNKNOWN
        result_tables: list[CheckFacts] = []
        for verification_result in ctx.dynamic_data.get("repo_verification", []):
            result_tables.append(
                ScmAuthenticityFacts(
                    repo_link=repo_link,
                    reason=verification_result.reason,
                    status=verification_result.status.value,
                    build_tool=verification_result.build_tool.name,
                    confidence=Confidence.MEDIUM,
                    stars_count=stars_count,
                    fork_count=fork_count,
                )
            )

            match (result_type, verification_result.status):
                case (_, RepositoryVerificationStatus.PASSED):
                    result_type = CheckResultType.PASSED
                case (CheckResultType.UNKNOWN, RepositoryVerificationStatus.FAILED):
                    result_type = CheckResultType.FAILED

        return CheckResultData(result_tables=result_tables, result_type=result_type)


registry.register(ScmAuthenticityCheck())
