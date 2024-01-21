# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the GitHub git service.
"""


from macaron.slsa_analyzer.git_service import GitHub

from ...macaron_testcase import MacaronTestCase


class TestGitHub(MacaronTestCase):
    """Test the GitHub git service."""

    def test_is_detected(self) -> None:
        """Test the is detected method."""
        github = GitHub()
        github.load_defaults()

        assert github.is_detected("http://github.com/org/name")
        assert github.is_detected("git@github.com:org/name")
        assert github.is_detected("git@github.com:7999/org/name")
        assert github.is_detected("ssh://git@github.com:7999/org/name")
        assert not github.is_detected("http://gitlab.com/org/name")
        assert not github.is_detected("git@github0.com:org/name")
        assert not github.is_detected("git@not-supported-git-host.com:7999/org/name")
        assert not github.is_detected("ssh://git@bitbucket.com:7999/org/name")
