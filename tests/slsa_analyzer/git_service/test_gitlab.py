# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the GitLab git service."""

import os
from unittest import mock

import pytest

from macaron.slsa_analyzer.git_service.gitlab import PublicGitLab


@pytest.mark.parametrize(
    ("repo_url"),
    [
        "https://gitlab.com/owner/repo.git",
        "https://gitlab.com/owner/repo",
    ],
)
def test_construct_clone_url_without_token(repo_url: str) -> None:
    """Test if the ``construct_clone_url`` method produces proper clone URLs without the access token."""
    clone_url = repo_url
    gitlab = PublicGitLab()
    gitlab.load_defaults()
    assert gitlab.construct_clone_url(repo_url) == clone_url


@pytest.mark.parametrize(
    ("repo_url", "clone_url"),
    [
        (
            "https://gitlab.com/owner/repo.git",
            "https://oauth2:abcxyz@gitlab.com/owner/repo.git",
        ),
        (
            "https://gitlab.com/owner/repo",
            "https://oauth2:abcxyz@gitlab.com/owner/repo",
        ),
    ],
)
def test_construct_clone_url_with_token(repo_url: str, clone_url: str) -> None:
    """Test if the ``construct_clone_url`` method produces proper clone URLs with the access token."""
    with mock.patch.dict(os.environ, {"MCN_PUBLIC_GITLAB_TOKEN": "abcxyz"}):
        gitlab = PublicGitLab()
        gitlab.load_defaults()
        assert gitlab.construct_clone_url(repo_url) == clone_url
