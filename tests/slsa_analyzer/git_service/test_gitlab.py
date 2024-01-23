# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the GitLab git service."""

import os
from pathlib import Path
from unittest import mock

import pytest
from pydriller.git import Git

from macaron.config.defaults import load_defaults
from macaron.errors import ConfigurationError
from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.git_service.gitlab import PubliclyHostedGitLab, SelfHostedGitLab
from tests.slsa_analyzer.mock_git_utils import commit_files, initiate_repo


@pytest.mark.parametrize(
    ("repo_url"),
    [
        "https://gitlab.com/owner/repo.git",
        "https://gitlab.com/owner/repo",
    ],
)
def test_construct_clone_url_without_token(repo_url: str) -> None:
    """Test if the ``construct_clone_url`` method produces proper clone URLs without the access token."""
    with mock.patch("macaron.config.global_config.global_config.gl_token", ""):
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
    with mock.patch("macaron.config.global_config.global_config.gl_token", "abcxyz"):
        gitlab = PubliclyHostedGitLab()
        gitlab.load_defaults()
        assert gitlab.construct_clone_url(repo_url) == clone_url


@pytest.mark.parametrize(
    ("user_config_input", "repo_url", "clone_url"),
    [
        pytest.param(
            """
            [git_service.gitlab.self_hosted]
            hostname = internal.gitlab.org
            """,
            "https://internal.gitlab.org/owner/repo.git",
            "https://oauth2:abcxyz@internal.gitlab.org/owner/repo.git",
            id="Self-hosted GitLab is set in user config.",
        ),
        pytest.param(
            """
            [git_service.gitlab.self_hosted]
            hostname = internal.gitlab.org
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

    with mock.patch("macaron.config.global_config.global_config.gl_self_host_token", "abcxyz"):
        gitlab = SelfHostedGitLab()
        gitlab.load_defaults()
        assert gitlab.construct_clone_url(repo_url) == clone_url


def test_self_hosted_gitlab_without_env_set(tmp_path: Path) -> None:
    """Test if the ``load_defaults`` method raises error if the required env variable is not set."""
    user_config_input = """
    [git_service.gitlab.self_hosted]
    hostname = internal.gitlab.org
    """
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)

    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)
    with mock.patch("macaron.config.global_config.global_config.gl_self_host_token", ""):
        gitlab = SelfHostedGitLab()

        with pytest.raises(ConfigurationError):
            gitlab.load_defaults()


@pytest.fixture(name="self_hosted_gitlab")
def self_hosted_gitlab_repo_fixture(request: pytest.FixtureRequest) -> Git:
    """Create a mock GitLab self_hosted repo.

    This fixture expects ONE parameter of type STR which will be the origin remote url initialized for the self_hosted
    GitLab repo. To see how we could utilize this with pytest.mark.parameterize, see:
    https://docs.pytest.org/en/7.1.x/example/parametrize.html?highlight=indirect#indirect-parametrization
    https://docs.pytest.org/en/7.1.x/example/parametrize.html?highlight=indirect#apply-indirect-on-particular-arguments

    Returns
    -------
    Git
        The pydriller.git.Git wrapper object for the self_hosted GitLab repo.
    """
    test_repo_path = Path(__file__).parent.joinpath("resources", "self_hosted_gitlab_repo")

    gitlab_repo = initiate_repo(test_repo_path)

    # Commit untracked test files in the mock repo.
    # This would only happen the first time this test case is run.
    if gitlab_repo.repo.untracked_files:
        commit_files(gitlab_repo, gitlab_repo.repo.untracked_files)

    # Assigning the origin remote url to the passed in parameter.
    remote_url = request.param

    # For newly init git repositories, the origin remote does not exist. Therefore, we create one and assign it with
    # ``remote_url``.
    # If the origin remote already exist we reset its URL to be the ``remote_url``.
    if "origin" not in gitlab_repo.repo.remotes:
        remote_name = "origin"
        gitlab_repo.repo.create_remote(remote_name, remote_url)
    else:
        gitlab_repo.repo.remote("origin").set_url(remote_url)

    yield gitlab_repo

    gitlab_repo.clear()


# The indirect parameter is used to note that ``self_hosted_gitlab`` should be passed to the ``self_hosted_gitlab``
# fixture first. The test function would then receive the final fixture value.
# As for ``expected_origin_url``, this parameter is passed directly into the test function because it's not listed in
# ``indirect``. Reference:
# https://docs.pytest.org/en/7.1.x/example/parametrize.html?highlight=indirect#apply-indirect-on-particular-arguments
@pytest.mark.parametrize(
    ("self_hosted_gitlab", "expected_origin_url"),
    [
        ("https://oauth2:abcxyz@internal.gitlab.org/a/b", "https://internal.gitlab.org/a/b"),
        ("https://oauth2:abcxyz@internal.gitlab.org/a/b.git", "https://internal.gitlab.org/a/b"),
    ],
    indirect=["self_hosted_gitlab"],
)
def test_origin_remote_url_masking(self_hosted_gitlab: Git, expected_origin_url: str, tmp_path: Path) -> None:
    """Test if the ``clone_repo`` and ``check_out_repo`` methods handle masking the token in the clone URL correctly.

    Note that this test ONLY checks if the remote origin URL after the clone/checkout operations is updated back to
    the token-less URL.
    It does not check whether those operation works correctly.
    """
    user_config_input = """
    [git_service.gitlab.self_hosted]
    hostname = internal.gitlab.org
    """
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)

    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)

    with mock.patch("macaron.config.global_config.global_config.gl_self_host_token", "abcxyz"):
        gitlab = SelfHostedGitLab()
        gitlab.load_defaults()

        with mock.patch("macaron.slsa_analyzer.git_url.clone_remote_repo", return_value=self_hosted_gitlab.repo):
            # We check the origin remote URL after cloning is as expected.
            gitlab.clone_repo(str(tmp_path), expected_origin_url)
            assert git_url.get_remote_origin_of_local_repo(self_hosted_gitlab) == expected_origin_url

        with mock.patch("macaron.slsa_analyzer.git_url.check_out_repo_target", return_value=self_hosted_gitlab.repo):
            # We check that after checking out the latest commit in the default branch, the origin remote
            # URL is as expected.
            gitlab.check_out_repo(self_hosted_gitlab, branch="", digest="", offline_mode=True)
            assert git_url.get_remote_origin_of_local_repo(self_hosted_gitlab) == expected_origin_url

            gitlab.check_out_repo(self_hosted_gitlab, branch="", digest="", offline_mode=False)
            assert git_url.get_remote_origin_of_local_repo(self_hosted_gitlab) == expected_origin_url
