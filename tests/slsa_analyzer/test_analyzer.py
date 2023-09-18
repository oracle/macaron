# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the slsa_analyzer.Gh module."""

from pathlib import Path

import pytest
from packageurl import PackageURL

from macaron.config.target_config import Configuration
from macaron.errors import InvalidPURLError
from macaron.slsa_analyzer.analyzer import Analyzer

from ..macaron_testcase import MacaronTestCase


class TestAnalyzer(MacaronTestCase):
    """
    This class contains all the tests for the Analyzer
    """

    # Using the parent dir of this module as a valid start dir.
    PARENT_DIR = str(Path(__file__).parent)

    # pylint: disable=protected-access
    def test_resolve_local_path(self) -> None:
        """Test the resolve local path method."""
        # Test resolving a path outside of the start_dir
        assert not Analyzer._resolve_local_path(self.PARENT_DIR, "../")
        assert not Analyzer._resolve_local_path(self.PARENT_DIR, "./../")
        assert not Analyzer._resolve_local_path(self.PARENT_DIR, "../../../../../")

        # Test resolving a non-existing dir
        assert not Analyzer._resolve_local_path(self.PARENT_DIR, "./this-should-not-exist")

        # Test with invalid start_dir
        assert not Analyzer._resolve_local_path("non-existing-dir", "./")

        # Test resolve successfully
        assert Analyzer._resolve_local_path(self.PARENT_DIR, "./") == self.PARENT_DIR
        assert Analyzer._resolve_local_path(self.PARENT_DIR, "././././") == self.PARENT_DIR


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


@pytest.mark.parametrize(
    ("config"),
    [
        (Configuration({"purl": "invalid-purl"})),
        (Configuration({"purl": "invalid-purl", "path": "https://github.com/apache/maven"})),
    ],
)
def test_resolve_analysis_target_invalid_purl(config: Configuration) -> None:
    """Test the resolve analysis target method with invalid inputs."""
    with pytest.raises(InvalidPURLError):
        Analyzer.to_analysis_target(config, [])
