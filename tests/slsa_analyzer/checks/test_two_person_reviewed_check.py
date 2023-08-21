# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the TwoPersonReviewed Check."""

import os

from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.git_service.api_client import GhAPIClient


class TestTwoPersonReviewedCheck:
    """
    Provide three test cases here
    """

    def test_two_person_reviewed_check(self) -> None:
        """This is a function check two-person reviewed."""
        # Without any reviewer
        assert self.check_a_review("micronaut-projects/micronaut-core", "9745") == CheckResultType.FAILED
        # # With unauthenticated reviewers
        # review_data = api_client.get_a_review('micronaut-projects/micronaut-core', '9530')
        # assert check_obj.run_check(None, check_result) == CheckResultType.FAILED
        # With authenticated reviewers
        assert self.check_a_review("micronaut-projects/micronaut-core", "9530") == CheckResultType.PASSED

    def check_a_review(self, repo_full_name: str, pr_id: str) -> CheckResultType:
        """
        Implement the function to fetch a review and checks for two-person review completion.

        Parameters
        ----------
        repo_full_name (String): The full name of the repo.
        pr_id (String): Identify which pull request.

        Returns
        -------
        CheckResultType: Result of the test.
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

        review_data = api_client.get_a_review(repo_full_name, str(pr_id))
        for review in review_data:
            if review["state"] == "APPROVED" or review["state"] == "CHANGES_REQUESTED":
                return CheckResultType.PASSED
        return CheckResultType.FAILED
