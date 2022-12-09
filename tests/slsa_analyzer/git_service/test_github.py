# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the GitHub git service.
"""

from unittest.mock import patch

from macaron.slsa_analyzer.git_service import GitHub
from macaron.slsa_analyzer.git_service.api_client import GhAPIClient

from ...macaron_testcase import MacaronTestCase


class TestGitHub(MacaronTestCase):
    """Test the GitHub git service."""

    def test_is_detected(self) -> None:
        """Test the is detected method."""

        github = GitHub()

        assert github.is_detected("http://github.com/org/name")
        assert github.is_detected("git@github.com:org/name")
        assert github.is_detected("git@github.com:7999/org/name")
        assert github.is_detected("ssh://git@github.com:7999/org/name")
        assert not github.is_detected("http://gitlab.com/org/name")
        assert not github.is_detected("git@githubb.com:org/name")
        assert not github.is_detected("git@not_supported_git_host.com:7999/org/name")
        assert not github.is_detected("ssh://git@bitbucket.com:7999/org/name")

    def test_can_clone_remote_repo(self) -> None:
        """Test the can clone remote repo method."""

        github = GitHub()
        with patch.object(GhAPIClient, "get_repo_data", return_value=True):
            assert github.can_clone_remote_repo("can_clone_repo_url")

        with patch.object(GhAPIClient, "get_repo_data", return_value=False):
            assert not github.can_clone_remote_repo("invalid_repo_url")
