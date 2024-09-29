# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This check analyzes a jar by calling a JVM-based cli tool."""

import logging

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.repo_finder.repo_finder_java import JavaRepoFinder
from macaron.repo_finder.repo_verifier import RepositoryVerificationStatus
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence
from macaron.slsa_analyzer.registry import registry

logger: logging.Logger = logging.getLogger(__name__)


class MavenRepoVerificationFacts(CheckFacts):
    """The ORM mapping for justifications in maven source repo check."""

    __tablename__ = "_maven_repo_verification_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    group: Mapped[str] = mapped_column(String, nullable=False)
    artifact: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    claimed_repo: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    build_tool: Mapped[str] = mapped_column(String, nullable=False)
    dd_star_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dd_fork_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dd_dep_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dd_repo_link: Mapped[str | None] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "_maven_repo_verification_check",
    }


class MavenRepoVerificationCheck(BaseCheck):
    """This check verifies that if a source repository claimed by a maven package is valid."""

    def __init__(self) -> None:
        """Initialize a check instance."""
        check_id = "mcn_maven_repo_verification_1"
        description = "Check if the source repository claimed by a maven package is valid."

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
        if ctx.component.type != "maven":
            return CheckResultData(result_tables=[], result_type=CheckResultType.UNKNOWN)

        dd_info = JavaRepoFinder.get_deps_dev_info(ctx.component.namespace, ctx.component.name, ctx.component.version)

        result_type = CheckResultType.UNKNOWN
        result_tables: list[CheckFacts] = []
        for verification_result in ctx.dynamic_data.get("repo_verification", []):
            result_tables.append(
                MavenRepoVerificationFacts(
                    group=ctx.component.namespace,
                    artifact=ctx.component.name,
                    version=ctx.component.version,
                    claimed_repo=ctx.component.repository.remote_path if ctx.component.repository else None,
                    reason=verification_result.reason,
                    status=verification_result.status.value,
                    build_tool=verification_result.build_tool.name,
                    dd_star_count=dd_info.get("star_count", None),
                    dd_fork_count=dd_info.get("fork_count", None),
                    dd_dep_count=dd_info.get("dep_count", None),
                    dd_repo_link=dd_info.get("repo_link", None),
                    confidence=Confidence.MEDIUM,
                )
            )

            match (result_type, verification_result.status):
                case (_, RepositoryVerificationStatus.PASSED):
                    result_type = CheckResultType.PASSED
                case (CheckResultType.UNKNOWN, RepositoryVerificationStatus.FAILED):
                    result_type = CheckResultType.FAILED

        return CheckResultData(result_tables=result_tables, result_type=result_type)


registry.register(MavenRepoVerificationCheck())
