# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the TwoPersonReviewedCheck class."""

import logging
import os

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from macaron.config.defaults import defaults
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
    # The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003
    __mapper_args__ = {
        "polymorphic_identity": "_two_person_reviewed_check",
    }


class TwoPersonReviewedCheck(BaseCheck):
    """This Check checks whether the target submitted code has been reviewed by two people."""

    def __init__(self) -> None:
        """Initiate the BuildScriptCheck instance."""
        check_id = "mcn_two_person_reviewed_1"
        description = "Check whether the submitted code has been reviewd by two people."
        depends_on: list[tuple[str, CheckResultType]] = []
        eval_reqs = [ReqName.TWO_PERSON_REVIEWED]
        super().__init__(
            check_id=check_id,
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            # result_on_skip=CheckResultType.FAILED,
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
        check_result["result_tables"] = [TwoPersonReviewedTable()]
        required_reviewers = defaults.get_list("check.two_person", "required_reviewers", fallback=[])
        logger.info("Reviewers number required: %s", {required_reviewers[0]})
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
        # Query the PR based on the branch name specified through user input tag.
        pr_objects_list = api_client.list_pull_requests(
            ctx.component.repository.full_name, ctx.component.repository.branch_name
        )
        merged_pr_num = 0  # Store the number of the PRs already been merged.
        pass_num = 0  # If the pull request has been reviewed by 2 person, then increase the count.
        for pr_object in pr_objects_list:
            pr_number = pr_object["number"] if pr_object is not None and "number" in pr_object else None
            if pr_number is None:
                continue
            pr_requester = pr_object.get("user", None).get("login", None)
            if pr_requester is None:
                continue
            merged_at = pr_object["merged_at"] if pr_object is not None and "merged_at" in pr_object else None
            if merged_at:  # Check the PR is merged or not.
                merged_pr_num += 1
                review_data = api_client.get_a_review(ctx.component.repository.full_name, str(pr_number))
                reviewers = set()  # Use a set to avoid duplicates.

                for review in review_data:
                    reviewer = review["user"]["login"]
                    if reviewer != pr_requester:
                        reviewers.add(reviewer)

                if len(reviewers) >= int(required_reviewers[0]):
                    pass_num += 1

        logger.info(
            "%d pull requests have been reviewed by at least two person, and the pass rate is %d / %d",
            pass_num,
            pass_num,
            merged_pr_num,
        )
        check_result["justification"].extend(
            [
                f"{str(pass_num)} pull requests have been reviewed by at least two person.",
                f"The pass rate is {str(pass_num)} / {str(merged_pr_num)}",
            ]
        )

        if pass_num == merged_pr_num:
            return CheckResultType.PASSED
        return CheckResultType.FAILED


registry.register(TwoPersonReviewedCheck())
