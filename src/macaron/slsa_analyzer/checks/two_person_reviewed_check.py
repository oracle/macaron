# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the TwoPersonReviewedCheck class."""

import logging
import os

import requests
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from macaron.config.defaults import defaults
from macaron.database.database_manager import ORMBase
from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
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
        description = "Check whether the merged pull requests has been reviewd and approved by at least one reviewer."
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
        # Your GitHub personal access token (replace with your own token)
        token = os.getenv("GITHUB_TOKEN")
        # GitHub GraphQL API endpoint
        url = "https://api.github.com/graphql"
        # Define the GraphQL query
        query = """
            query ($owner: String!, $name: String!, $cursor: String, $branch_name: String) {
                repository(owner: $owner, name: $name) {
                    pullRequests(first: 100, states: MERGED, after: $cursor, baseRefName: $branch_name) {
                        totalCount
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                        edges {
                            node {
                                reviewDecision
                            }
                        }
                    }
                }
            }
        """
        # Set up the HTTP headers with your token
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        # Send the GraphQL query to GitHub API.
        # 100 data per query.
        approved_pr_num = 0
        merged_pr_num = 0
        has_next_page = True
        end_cursor = None

        while has_next_page:
            variables = {
                "owner": ctx.component.repository.owner,
                "name": ctx.component.repository.name,
                "cursor": end_cursor,
                "branch_name": ctx.component.repository.branch_name,
            }
            response = requests.post(
                url,
                timeout=defaults.getint("requests", "timeout", fallback=10),
                json={"query": query, "variables": variables},
                headers=headers,
            )  # nosec B113:request_without_timeout
            if response.status_code == 200:
                data = response.json()
                merged_pr_num = data["data"]["repository"]["pullRequests"]["totalCount"]
                for edge in data["data"]["repository"]["pullRequests"]["edges"]:
                    review_decision = edge["node"]["reviewDecision"]
                    if review_decision == "APPROVED":
                        approved_pr_num += 1
                has_next_page = data["data"]["repository"]["pullRequests"]["pageInfo"]["hasNextPage"]
                end_cursor = data["data"]["repository"]["pullRequests"]["pageInfo"]["endCursor"]
            else:
                logger.error("%s, %s", response.status_code, response.text)

        logger.info(
            "%d pull requests have been reviewed by at least two person, and the pass rate is %d / %d",
            approved_pr_num,
            approved_pr_num,
            merged_pr_num,
        )
        check_result["justification"].extend(
            [
                f"{str(approved_pr_num)} pull requests have been reviewed by at least two person.",
                f"The pass rate is {str(approved_pr_num)} / {str(merged_pr_num)}",
            ]
        )
        # print(f"[*] Two-person Reviewed in {duration} seconds")
        if approved_pr_num == merged_pr_num:
            return CheckResultType.PASSED
        return CheckResultType.FAILED


registry.register(TwoPersonReviewedCheck())
