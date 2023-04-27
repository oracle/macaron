# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the generic actions on Git repositories."""

import os
from pathlib import Path

from macaron.config.defaults import defaults
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
        "ssh://git@github.com:8080/invalid/repo/name",
        "https://gitlab.com/invalid/repo/name.git",
        "ssh://git@github.com:8080/",
        "git@gitlab.com:owner/invalid/repo/name.git",
    ]

    # Test get repo name
    assert all(git_url.get_repo_name_from_url(url) == repo_name for url in valid_git_urls)
    assert not all(git_url.get_repo_name_from_url(url) for url in invalid_git_urls)

    # Test get repo full name
    assert all(git_url.get_repo_full_name_from_url(url) == repo_full_name for url in valid_git_urls)
    assert not all(git_url.get_repo_full_name_from_url(url) for url in invalid_git_urls)


def test_clone_remote_repo() -> None:
    """
    Test the clone remote repository method
    """
    assert not git_url.clone_remote_repo(str(Path(__file__).parent), "")


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
    not_remote_urls = ["", "/home/user/repo"]
    assert all(git_url.is_remote_repo(url) for url in remote_urls)
    assert not all(git_url.is_remote_repo(url) for url in not_remote_urls)


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


def test_invalid_git_allowed_hosts() -> None:
    """Test the vcs URL validator method without any allowed git hosts."""
    original_allowed_hosts = defaults.get("git", "allowed_hosts")

    # Test running with no git hosts defined in defaults.ini
    defaults.remove_option("git", "allowed_hosts")
    assert git_url.get_remote_vcs_url("https://github.com/org/name.git") == ""
    assert git_url.get_remote_vcs_url("https://gitlab.com/org") == ""

    # Test running with invalid git hosts defined in defaults.ini
    defaults["git"]["allowed_hosts"] = "invalid host"
    assert git_url.get_remote_vcs_url("https://github.com/org/name.git") == ""
    assert git_url.get_remote_vcs_url("https://gitlab.com/org") == ""

    defaults["git"]["allowed_hosts"] = original_allowed_hosts


def test_get_unique_path() -> None:
    """Test the get unique path method."""
    assert git_url.get_repo_dir_name("https://github.com/apache/maven") == os.path.normpath("github_com/apache/maven")
    assert git_url.get_repo_dir_name("https://gitlab.com/apache/maven") == os.path.normpath("gitlab_com/apache/maven")
    assert git_url.get_repo_dir_name("git@github.com:apache/maven") == os.path.normpath("github_com/apache/maven")

    # TODO: use pytest fixtures to properly set and cleanup defaults after each run.
    back_up = defaults["git"]["allowed_hosts"]
    defaults["git"]["allowed_hosts"] = f"{back_up} git.host.blah ** wrong_host##format"

    assert git_url.get_repo_dir_name("git@git.host.blah:apache/maven") == os.path.normpath("git_host_blah/apache/maven")
    assert git_url.get_repo_dir_name("https://**/apache/maven") == os.path.normpath("mcn__/apache/maven")
    assert git_url.get_repo_dir_name("https://wrong_host##format/apache/maven") == ""
    assert git_url.get_repo_dir_name("git@not.supported.githost.com/apache/maven") == ""

    defaults["git"]["allowed_hosts"] = back_up
