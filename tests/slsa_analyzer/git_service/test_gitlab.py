# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the GitLab git service."""

import os
from pathlib import Path
from unittest import mock

import pytest

from macaron.config.defaults import load_defaults
from macaron.errors import ConfigurationError
from macaron.slsa_analyzer.git_service.gitlab import PubliclyHostedGitLab, SelfHostedGitLab


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
    gitlab = PubliclyHostedGitLab()
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
    with mock.patch.dict(os.environ, {"MCN_GITLAB_TOKEN": "abcxyz"}):
        gitlab = PubliclyHostedGitLab()
        gitlab.load_defaults()
        assert gitlab.construct_clone_url(repo_url) == clone_url


@pytest.mark.parametrize(
    ("user_config_input", "repo_url", "clone_url"),
    [
        pytest.param(
            """
            [git_service.gitlab.self_hosted]
            domain = internal.gitlab.org
            """,
            "https://internal.gitlab.org/owner/repo.git",
            "https://oauth2:abcxyz@internal.gitlab.org/owner/repo.git",
            id="Self-hosted GitLab is set in user config.",
        ),
        pytest.param(
            """
            [git_service.gitlab.self_hosted]
            domain = internal.gitlab.org
            """,
            "https://internal.gitlab.org/owner/repo",
            "https://oauth2:abcxyz@internal.gitlab.org/owner/repo",
            id="Self-hosted GitLab is set in user config.",
        ),
    ],
)
def test_construct_clone_url_for_self_hosted_gitlab(
    user_config_input: str, repo_url: str, clone_url: str, tmp_path: Path
) -> None:
    """Test if the ``construct_clone_url`` method produces proper clone URLs with the access token."""
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)
    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)

    with mock.patch.dict(os.environ, {"MCN_SELF_HOSTED_GITLAB_TOKEN": "abcxyz"}):
        gitlab = SelfHostedGitLab()
        gitlab.load_defaults()
        assert gitlab.construct_clone_url(repo_url) == clone_url


def test_self_hosted_gitlab_without_env_set(tmp_path: Path) -> None:
    """Test if the ``load_defaults`` method raises error if the required env variable is not set."""
    user_config_input = """
    [git_service.gitlab.self_hosted]
    domain = internal.gitlab.org
    """
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)

    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)

    with mock.patch.dict(os.environ, {"MCN_SELF_HOSTED_GITLAB_TOKEN": ""}):
        gitlab = SelfHostedGitLab()

        with pytest.raises(ConfigurationError):
            gitlab.load_defaults()
