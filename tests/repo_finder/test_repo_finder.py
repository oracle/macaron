# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the repo finder."""
import os
from pathlib import Path

import pytest
from packageurl import PackageURL
from pydriller import Git

from macaron.config.target_config import Configuration
from macaron.repo_finder import repo_finder
from macaron.slsa_analyzer.analyzer import Analyzer
from tests.slsa_analyzer.mock_git_utils import add_tag_if_not_present, commit_files, initiate_repo


@pytest.mark.parametrize(
    ("config", "available_domains", "expect"),
    [
        (
            Configuration({"purl": ""}),
            ["github.com", "gitlab.com", "bitbucket.org"],
            Analyzer.AnalysisTarget(parsed_purl=None, repo_path="", branch="", digest=""),
        ),
        (
            Configuration({"purl": "pkg:github.com/apache/maven"}),
            ["github.com", "gitlab.com", "bitbucket.org"],
            Analyzer.AnalysisTarget(
                parsed_purl=PackageURL.from_string("pkg:github.com/apache/maven"),
                repo_path="https://github.com/apache/maven",
                branch="",
                digest="",
            ),
        ),
        (
            Configuration({"purl": "", "path": "https://github.com/apache/maven"}),
            ["github.com", "gitlab.com", "bitbucket.org"],
            Analyzer.AnalysisTarget(
                parsed_purl=None, repo_path="https://github.com/apache/maven", branch="", digest=""
            ),
        ),
        (
            Configuration({"purl": "pkg:maven/apache/maven", "path": "https://github.com/apache/maven"}),
            ["github.com", "gitlab.com", "bitbucket.org"],
            Analyzer.AnalysisTarget(
                parsed_purl=PackageURL.from_string("pkg:maven/apache/maven"),
                repo_path="https://github.com/apache/maven",
                branch="",
                digest="",
            ),
        ),
        (
            Configuration(
                {
                    "purl": "pkg:maven/apache/maven",
                    "path": "https://github.com/apache/maven",
                    "branch": "master",
                    "digest": "abcxyz",
                }
            ),
            ["github.com", "gitlab.com", "bitbucket.org"],
            Analyzer.AnalysisTarget(
                parsed_purl=PackageURL.from_string("pkg:maven/apache/maven"),
                repo_path="https://github.com/apache/maven",
                branch="master",
                digest="abcxyz",
            ),
        ),
    ],
)
def test_resolve_analysis_target(
    config: Configuration, available_domains: list[str], expect: Analyzer.AnalysisTarget
) -> None:
    """Test the resolve analysis target method with valid inputs."""
    assert Analyzer.to_analysis_target(config, available_domains) == expect


def test_get_commit_from_version_tag() -> None:
    """Test resolving commits from version tags."""
    path = Path(__file__).parent.joinpath("mock_repo")
    init_repo = not os.path.exists(path)
    git_obj: Git = initiate_repo(path)
    if init_repo:
        tags = [
            "test-name-v1.0.1-A",
            "v1.0.1-B",
            "v1.0.3+test",
            "1.0.5",
            "50.0",
            "78A",
        ]
        files = [path.joinpath(".git", "description")]
        # Add a commit for each tag with a message that can be verified later.
        for count, value in enumerate(tags):
            commit_files(git_obj, files, str(count))
            add_tag_if_not_present(git_obj, value)

    # Perform tests
    versions = [
        "1.0.1-A",
        "1.0.1-B",
        "1.0.3+test",
        "1.0.5",
        "50.0",
        "78A",
    ]
    purl_name = "test-name"
    for count, value in enumerate(versions):
        _test_tag(git_obj, PackageURL(type="maven", name=purl_name, version=value), str(count))
        purl_name = purl_name + "-" + str(count)


def _test_tag(git_obj: Git, purl: PackageURL, commit_message: str) -> None:
    """Retrieve commit matching tag and check commit message is correct."""
    branch, digest = repo_finder.get_commit_from_version_tag(git_obj, purl)
    assert branch
    assert git_obj.get_commit(digest).msg == commit_message
