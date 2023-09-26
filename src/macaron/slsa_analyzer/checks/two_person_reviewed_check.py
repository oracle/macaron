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
        token = os.getenv("GITHUB_TOKEN")
        gh_api_client = GhAPIClient(
            {
                "headers": {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                "query": """
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
                                    author {
                                        login
                                    }
                                    mergedBy {
                                        login
                                    }
                                }
                            }
                        }
                    }
                }
            """,
            }
        )
        # TODO filter mannequin from with merge-by
        # GitHub GraphQL API endpoint
        url = "https://api.github.com/graphql"

        approved_pr_num = 0
        merged_pr_num = 0
        has_next_page = True
        end_cursor = None
        dependabot_num = 0

        while has_next_page:
            variables = {
                "owner": ctx.component.repository.owner,
                "name": ctx.component.repository.name,
                "cursor": end_cursor,
                "branch_name": ctx.component.repository.branch_name,
            }
            pull_requests = gh_api_client.graphql_fetch_pull_requests(url=url, variables=variables)
            merged_pr_num = pull_requests["merged_pr_num"]
            has_next_page = pull_requests["has_next_page"]
            end_cursor = pull_requests["end_cursor"]
            approved_pr_num += pull_requests["approved_pr_num"]
            dependabot_num += pull_requests["dependabot_num"]

        logger.info(
            "%d pull requests have been reviewed by at least two person, and the pass rate is %d / %d",
            approved_pr_num,
            approved_pr_num,
            merged_pr_num - dependabot_num,
        )
        check_result["justification"].extend(
            [
                f"{str(approved_pr_num)} pull requests have been reviewed by at least two person.",
                f"The pass rate is {str(approved_pr_num)} / {str(merged_pr_num)}",
            ]
        )
        if approved_pr_num == merged_pr_num:
            return CheckResultType.PASSED
        return CheckResultType.FAILED


registry.register(TwoPersonReviewedCheck())
