# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the TwoPersonReviewedCheck class."""

import logging
import os

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.database.database_manager import ORMBase
from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.git_service.api_client import GhAPIClient
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class TwoPersonReviewedTable(CheckFacts, ORMBase):
    """Check result table for two-person_reviewed."""

    __tablename__ = "_two_person_reviewed_check"
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    failed_pr_id: Mapped[str] = mapped_column(String, nullable=False)
    # repo_name: Mapped[str] = mapped_column(String, nullable=False)
    # reviewer_name: Mapped[str] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "_two_person_reviewed_check",
    }


class TwoPersonReviewedCheck(BaseCheck):
    """This Check checks whether the target submitted code has been reviewed by two people."""

    def __init__(self) -> None:
        """Initiate the BuildScriptCheck instance."""
        check_id = "mcn_two_person_reviewed_1"
        description = "Check whether the submitted code has been reviewd by two people."
        # depends_on: list[tuple[str, CheckResultType]] = [("mcn_provenance_available_1", CheckResultType.PASSED)]
        depends_on: list[tuple[str, CheckResultType]] = []
        eval_reqs = [ReqName.TWO_PERSON_REVIEWED]
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
        api_client = GhAPIClient(
            {
                "headers": {
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN')}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                "query": [],
            }
        )

        pr_ids_list = api_client.list_pull_requests(ctx.component.repository.full_name)
        pr_ids_len = len(pr_ids_list)
        pass_num = 0  # If the pull request has been reviewed by 2 person, then add the number.
        for pr_id in pr_ids_list:
            review_data = api_client.get_a_review(ctx.component.repository.full_name, str(pr_id))
            reviewers = set()  # Use a set to avoid duplicates
            for review in review_data:
                if review["state"] == "APPROVED" or review["state"] == "CHANGES_REQUESTED":
                    reviewers.add(review["user"]["login"])
                    pass_num += 1

        logger.info(
            "%d pull requests have been reviewed by at least two person, and the pass rate is %d / %d",
            pass_num,
            pass_num,
            pr_ids_len,
        )
        check_result["justification"].extend(
            [
                {
                    f"{pass_num} pull requests have been reviewed by at least two person."
                    "The pass rate is {pass_num} / ": str(pr_ids_len)
                }
            ]
        )

        if pass_num == pr_ids_len:
            return CheckResultType.PASSED
        return CheckResultType.FAILED


registry.register(TwoPersonReviewedCheck())
