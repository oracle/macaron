# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the repo finder."""

import pytest
from packageurl import PackageURL

from macaron.config.target_config import Configuration
from macaron.slsa_analyzer.analyzer import Analyzer


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
