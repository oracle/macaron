# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the GhAPIClient module
"""

from unittest import TestCase

from macaron.slsa_analyzer.git_service.api_client import GhAPIClient


class TestGhAPIClient(TestCase):
    """
    This test provide tests for the GhAPIClient class
    """

    mock_profile = {
        "headers": {
            "Authorization": "sample_token",
            "Accept": "application/vnd.github.v3+json",
        },
        "query": ["java+language:java"],
    }

    error_mock_profile = {"wrong_field": "Wrong data"}

    mock_query_list = ["java+language:java"]

    def test_init(self) -> None:
        """
        Test if the search client is initiated correctly.
        """
        client = GhAPIClient(self.mock_profile)
        assert client.headers == {
            "Authorization": "sample_token",
            "Accept": "application/vnd.github.v3+json",
        }
        assert client.query_list == self.mock_query_list

        # Invalid profile
        self.assertRaises(KeyError, GhAPIClient, self.error_mock_profile)

    def test_get_permanent_link(self) -> None:
        """Test the get permanent link method."""
        client = GhAPIClient(self.mock_profile)
        full_name = "owner/repo"
        commit_sha = "aaaad19541e0bbfef111116eff65fdea00eeeed1"
        file_path = ".travis_ci.yml"
        expected_link = f"https://github.com/owner/repo/blob/{commit_sha}/{file_path}"
        assert client.get_file_link(full_name, commit_sha, file_path) == expected_link

    def test_get_relative_path_of_workflow(self) -> None:
        """Test the get relative path of workflow method."""
        client = GhAPIClient(self.mock_profile)
        workflow_name = "maven.yaml"
        expected_path = f".github/workflows/{workflow_name}"
        assert client.get_relative_path_of_workflow(workflow_name) == expected_path
