# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the generic actions on Git repositories."""

import configparser
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from macaron.slsa_analyzer import git_url


def test_get_repo_name_from_url() -> None:
    """
    Test the extract repo name and full name from url method
    """
    repo_name = "repo_name"
    repo_full_name = "owner/repo_name"

    valid_git_urls = [
        f"git@github.com:owner/{repo_name}.git",
        f"git@gitlab.com:owner/{repo_name}.git",
        f"https://gitlab.com/owner/{repo_name}",
        f"https://github.com/owner/{repo_name}.git",
        f"https://github.com/owner/{repo_name}",
        f"git+https://github.com/owner/{repo_name}",
        f"git+ssh://git@github.com/owner/{repo_name}.git",
        f"git+ssh://git@github.com/owner/{repo_name}",
        f"git+ssh://git@github.com:owner/{repo_name}.git",
        f"git+ssh://git@github.com:8080/owner/{repo_name}",
        f"ssh://git@github.com/owner/{repo_name}.git",
        f"ssh://git@github.com/owner/{repo_name}",
        f"ssh://git@github.com:owner/{repo_name}.git",
        f"ssh://git@github.com:8080/owner/{repo_name}",
        f"scm:ssh://git@github.com:8080/owner/{repo_name}",
    ]
    invalid_git_urls = [
        "",
        f"{repo_name}.git",
        f"{repo_name}.git/",
        "ssh://git@github.com:8080/invalid/",
        "https://gitlab.com/invalid.git",
        "ssh://git@github.com:8080/",
        "git@gitlab.com:owner",
    ]

    # Test get repo name
    assert all(git_url.get_repo_name_from_url(url) == repo_name for url in valid_git_urls)
    assert not any(git_url.get_repo_name_from_url(url) for url in invalid_git_urls)

    # Test get repo full name
    assert all(git_url.get_repo_full_name_from_url(url) == repo_full_name for url in valid_git_urls)
    assert not any(git_url.get_repo_full_name_from_url(url) for url in invalid_git_urls)


def test_is_remote_repo() -> None:
    """
    Test the is_remote_repo method
    """
    repo_name = "repo_name"
    remote_urls = [
        f"git@github.com:owner/{repo_name}.git",
        f"git@gitlab.com:owner/{repo_name}.git",
        f"https://gitlab.com/owner/{repo_name}",
        f"https://github.com/owner/{repo_name}.git",
        f"https://github.com/owner/{repo_name}",
        f"git+https://github.com/owner/{repo_name}",
    ]
    not_remote_urls = ["", "/home/user/repo", "https://invalid/repo/name"]
    assert all(git_url.is_remote_repo(url) for url in remote_urls)
    assert not any(git_url.is_remote_repo(url) for url in not_remote_urls)


def test_clean_up_repo_path() -> None:
    """Test the clean up repo path method."""
    assert git_url.clean_up_repo_path("https://github.com/org/name///") == "https://github.com/org/name"
    assert git_url.clean_up_repo_path("https://github.com/org/name///     ") == "https://github.com/org/name"
    assert git_url.clean_up_repo_path("https://gitlab.com/org/name///     ") == "https://gitlab.com/org/name"
    assert git_url.clean_up_repo_path("ssh://git@github.com:org/name.git") == "ssh://git@github.com:org/name"
    assert git_url.clean_up_repo_path("ssh://git@gitlab.com:org/name.git") == "ssh://git@gitlab.com:org/name"
    assert git_url.clean_up_repo_path("https://github.com/xmlunit/xmlunit.git") == "https://github.com/xmlunit/xmlunit"
    assert git_url.clean_up_repo_path("https://github.com/xmlunit/xmlunit") == "https://github.com/xmlunit/xmlunit"
    assert git_url.clean_up_repo_path("https://gitlab.com/xmlunit/xmlunit") == "https://gitlab.com/xmlunit/xmlunit"


def test_get_remote_vcs_url() -> None:
    """Test the vcs URL validator method."""
    assert git_url.get_remote_vcs_url("https://github.com/org/name/foo/bar") == "https://github.com/org/name"
    assert git_url.get_remote_vcs_url("https://github.com/org/name.git") == "https://github.com/org/name"
    assert git_url.get_remote_vcs_url("https://github.com/org/name.git", False) == "https://github.com/org/name.git"
    assert git_url.get_remote_vcs_url("git@github.com:org/name/") == "https://github.com/org/name"
    assert git_url.get_remote_vcs_url("git@gitlab.com:org/name/") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("git@gitlab.com:7999/org/name/") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("git@gitlab.com:/org/name/") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("https://github.com/org/name///") == "https://github.com/org/name"
    assert git_url.get_remote_vcs_url("https://github.com/org/name///     ") == "https://github.com/org/name"
    assert git_url.get_remote_vcs_url("http://github.com/org/name///     ") == "https://github.com/org/name"
    assert git_url.get_remote_vcs_url("git+https://gitlab.com/org/name/") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("git+ssh://git@gitlab.com/org/name/") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("scm:git+https://gitlab.com/org/name/") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("git+ssh://git@gitlab.com:8000/org/name/") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("ssh://git@gitlab.com:org/name/") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("ssh://git@gitlab.com/org/name/foo/bar") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("git@github.com:7999org/name") == "https://github.com/7999org/name"
    assert git_url.get_remote_vcs_url("git:ssh://git@gitlab.com/org/name/foo/bar") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("scm:ssh://git@gitlab.com/org/name/foo/bar") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("scm:git+ssh://git@gitlab.com/org/name/foo/bar") == "https://gitlab.com/org/name"
    assert git_url.get_remote_vcs_url("ssh://gitlab.com/org/name/") == ""
    assert git_url.get_remote_vcs_url("ssh://gitlab.com:org/name.git") == ""
    assert git_url.get_remote_vcs_url("https://github.com/org") == ""
    assert git_url.get_remote_vcs_url("https://example.com") == ""
    assert git_url.get_remote_vcs_url("https://unsupport.host.com/org/name") == ""
    assert git_url.get_remote_vcs_url("git@unsupport.host.com:org/name/") == ""
    assert git_url.get_remote_vcs_url("git@github.com:org/") == ""
    assert git_url.get_remote_vcs_url("git@github.com:7999/org/") == ""


@pytest.mark.parametrize(
    ("config_input", "expected_allowed_domain_set"),
    [
        (
            """
            [git_service.github]
            domain = github.com

            [git_service.gitlab.public]
            domain = gitlab.com
            """,
            {"github.com", "gitlab.com"},
        ),
        (
            """
            [git_service.gitlab.public]
            domain = gitlab.com

            [git_service.gitlab.private]
            domain = internal.gitlab.org
            """,
            {"gitlab.com", "internal.gitlab.org"},
        ),
    ],
)
def test_get_allowed_git_service_domains(
    config_input: str,
    expected_allowed_domain_set: set[str],
) -> None:
    """Test the get allowed git service domains function."""
    config = configparser.ConfigParser()
    config.read_string(config_input)
    assert set(git_url.get_allowed_git_service_domains(config)) == expected_allowed_domain_set


@pytest.mark.parametrize(
    ("default_config_input", "override_config_input", "expected_allowed_domain_set"),
    [
        pytest.param(
            # The current behavior is: we always enable GitHub and public GitLab by default.
            # User config cannot disable either of the two.
            """
            [git_service.github]
            domain = github.com

            [git_service.gitlab.public]
            domain = gitlab.com
            """,
            """
            [git_service.github]
            domain = github.com
            """,
            {"github.com", "gitlab.com"},
            id="Only GitHub in user config",
        ),
        pytest.param(
            """
            [git_service.github]
            domain = github.com

            [git_service.gitlab.public]
            domain = gitlab.com
            """,
            """
            [git_service.gitlab.private]
            domain = internal.gitlab.org
            """,
            {"github.com", "gitlab.com", "internal.gitlab.org"},
            id="Private GitLab in user config",
        ),
    ],
)
def test_get_allowed_git_service_domains_with_override(
    default_config_input: str,
    override_config_input: str,
    expected_allowed_domain_set: set[str],
    tmp_path: Path,
) -> None:
    """Test the get allowed git service domains function, in multi-config files scenario."""
    default_filepath = tmp_path / "default.ini"
    override_filepath = tmp_path / "override.ini"
    with open(default_filepath, "w", encoding="utf-8") as default_file:
        default_file.write(default_config_input)
    with open(override_filepath, "w", encoding="utf-8") as override_file:
        override_file.write(override_config_input)

    config = configparser.ConfigParser()
    config.read([default_filepath, override_filepath])

    assert set(git_url.get_allowed_git_service_domains(config)) == expected_allowed_domain_set


@patch("macaron.slsa_analyzer.git_url.get_allowed_git_service_domains")
def test_get_remote_vcs_url_with_invalid_allowed_domains(
    get_allowed_domains_fn: MagicMock,
) -> None:
    """Test the vcs URL validator method without any allowed git hosts."""
    get_allowed_domains_fn.return_value = []
    assert git_url.get_remote_vcs_url("https://github.com/org/name.git") == ""
    assert git_url.get_remote_vcs_url("https://gitlab.com/org") == ""

    get_allowed_domains_fn.return_value = ["invalid host"]
    assert git_url.get_remote_vcs_url("https://github.com/org/name.git") == ""
    assert git_url.get_remote_vcs_url("https://gitlab.com/org") == ""


@pytest.mark.parametrize(
    ("url", "path"),
    [
        ("https://github.com/apache/maven", "github_com/apache/maven"),
        ("https://gitlab.com/apache/maven", "gitlab_com/apache/maven"),
        ("git@github.com:apache/maven", "github_com/apache/maven"),
    ],
)
def test_get_unique_path(url: str, path: str) -> None:
    """Test the get unique path method."""
    assert git_url.get_repo_dir_name(url) == os.path.normpath(path)
