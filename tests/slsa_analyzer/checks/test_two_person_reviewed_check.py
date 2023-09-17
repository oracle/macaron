# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the TwoPersonReviewed Check."""
import logging
import os

import requests

from macaron.config.defaults import defaults

logger: logging.Logger = logging.getLogger(__name__)


class TestTwoPersonReviewedCheck:
    """
    Provide three test cases here
    """

    def test_two_person_reviewed_check(self) -> None:
        """This is a function check two-person reviewed."""
        # Change request merged pull request
        assert self.check_a_review("micronaut-projects", "micronaut-core", 593) == "CHANGES_REQUESTED"
        # Approved merged pull request
        assert self.check_a_review("micronaut-projects", "micronaut-core", 9875) == "APPROVED"

    def check_a_review(self, owner: str, name: str, pr_number: int) -> str:
        """
        Implement the function to fetch a review and checks for two-person review completion.

        Parameters
        ----------
        owner (String): The name of the owner.
        name (String): The name of the repo.
        pr_number (String): Identify which pull request.

        Returns
        -------
        CheckResultType: Result of the test.
        """
        # Your GitHub personal access token (replace with your own token)
        token = os.getenv("GITHUB_TOKEN")
        # GitHub GraphQL API endpoint
        url = "https://api.github.com/graphql"
        # Define the GraphQL query
        query = """
            query ($owner: String!, $name: String!, $number: Int!) {
                repository(owner: $owner, name: $name) {
                    pullRequest(number: $number) {
                        reviewDecision
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
        variables = {
            "owner": owner,
            "name": name,
            "number": pr_number,
        }
        response = requests.post(
            url,
            timeout=defaults.getint("requests", "timeout", fallback=10),
            json={"query": query, "variables": variables},
            headers=headers,
        )  # nosec B113:request_without_timeout
        review_decision = ""
        if response.status_code == 200:
            data = response.json()
            review_decision = data["data"]["repository"]["pullRequest"]["reviewDecision"]
        else:
            logger.error("%s, %s", response.status_code, response.text)

        return review_decision
