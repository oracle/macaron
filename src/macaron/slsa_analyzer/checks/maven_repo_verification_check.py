# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""A check to determine whether the source repository of a maven package can be independently verified."""

import logging

from packageurl import PackageURL
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.repo_finder.repo_finder_deps_dev import DepsDevRepoFinder
from macaron.repo_verifier.repo_verifier_base import RepositoryVerificationStatus
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

    # Repository link identified by Macaron's repo finder.
    repo_link: Mapped[str] = mapped_column(String, nullable=True)

    # Repository link identified by deps.dev.
    deps_dev_repo_link: Mapped[str | None] = mapped_column(String, nullable=True)

    # Number of stars on the repository identified by deps.dev.
    deps_dev_stars_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Number of forks on the repository identified by deps.dev.
    deps_dev_fork_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # The status of the check: passed, failed, or unknown.
    status: Mapped[str] = mapped_column(String, nullable=False)

    # The reason for the status.
    reason: Mapped[str] = mapped_column(String, nullable=False)

    # The build tool used to build the package.
    build_tool: Mapped[str] = mapped_column(String, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "_maven_repo_verification_check",
    }


class MavenRepoVerificationCheck(BaseCheck):
    """Check whether the claims of a source repository provenance made by a maven package can be independently verified."""

    def __init__(self) -> None:
        """Initialize a check instance."""
        check_id = "mcn_maven_repo_verification_1"
        description = (
            "Check whether the claims of a source repository provenance"
            " made by a maven package can be independently verified."
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
        if ctx.component.type != "maven":
            return CheckResultData(result_tables=[], result_type=CheckResultType.UNKNOWN)

        deps_dev_repo_finder = DepsDevRepoFinder()
        deps_dev_repo_link = deps_dev_repo_finder.find_repo(PackageURL.from_string(ctx.component.purl))
        deps_dev_repo_info = deps_dev_repo_finder.get_project_info(deps_dev_repo_link)

        stars_count: int | None = None
        fork_count: int | None = None

        if deps_dev_repo_info:
            stars_count = deps_dev_repo_info.get("starsCount")
            fork_count = deps_dev_repo_info.get("forksCount")

        result_type = CheckResultType.UNKNOWN
        result_tables: list[CheckFacts] = []
        for verification_result in ctx.dynamic_data.get("repo_verification", []):
            result_tables.append(
                MavenRepoVerificationFacts(
                    group=ctx.component.namespace,
                    artifact=ctx.component.name,
                    version=ctx.component.version,
                    repo_link=ctx.component.repository.remote_path if ctx.component.repository else None,
                    reason=verification_result.reason,
                    status=verification_result.status.value,
                    build_tool=verification_result.build_tool.name,
                    confidence=Confidence.MEDIUM,
                    deps_dev_repo_link=deps_dev_repo_link,
                    deps_dev_stars_count=stars_count,
                    deps_dev_fork_count=fork_count,
                )
            )

            match (result_type, verification_result.status):
                case (_, RepositoryVerificationStatus.PASSED):
                    result_type = CheckResultType.PASSED
                case (CheckResultType.UNKNOWN, RepositoryVerificationStatus.FAILED):
                    result_type = CheckResultType.FAILED

        return CheckResultData(result_tables=result_tables, result_type=result_type)


registry.register(MavenRepoVerificationCheck())
