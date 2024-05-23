# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the slsa_analyzer.Gh module."""

from pathlib import Path

import hypothesis.provisional as st_pr
import hypothesis.strategies as st
import pytest
from hypothesis import given
from packageurl import PackageURL

from macaron.config.target_config import Configuration
from macaron.errors import InvalidAnalysisTargetError, InvalidPURLError
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
    parsed_purl = Analyzer.parse_purl(config)
    assert Analyzer.to_analysis_target(config, available_domains, parsed_purl) == expect


@given(
    purl_type=st.one_of(st.text(), st.sampled_from(["maven", "npm", "pypi", "github.com"])),
    namespace=st.one_of(st.none(), st.text()),
    artifact_id=st.text(),
    version=st.text(),
    url=st_pr.urls(),
    branch=st.text(),
    digest=st.text(),
    available_domains=st.just(["github.com", "gitlab.com", "bitbucket.org"]),
)
def test_invalid_analysis_target(
    purl_type: str,
    namespace: str | None,
    artifact_id: str,
    version: str,
    url: str,
    branch: str,
    digest: str,
    available_domains: list[str],
) -> None:
    """Test the analysis target resolution with invalid inputs."""
    config = Configuration(
        {
            "purl": f"pkg:{purl_type}/{namespace}/{artifact_id}@{version}",
            "path": url,
            "branch": branch,
            "digest": digest,
        }
    )
    try:
        purl = Analyzer.parse_purl(config)
        Analyzer.to_analysis_target(config, available_domains, purl)
    except InvalidPURLError:
        pass


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
        Analyzer.parse_purl(config)


def test_resolve_analysis_target_no_purl_or_repository() -> None:
    """Test creation of an Analysis Target when no PURL or repository path is provided."""
    with pytest.raises(InvalidAnalysisTargetError):
        Analyzer.to_analysis_target(Configuration(), [], None)


@pytest.mark.parametrize(
    ("url", "purl_string", "expected"),
    [
        ("https://github.com:9000/oracle/macaron", "pkg:github/oracle/macaron", True),
        ("http://user:pass@github.com/oracle/macaron", "pkg:github.com/oracle/macaron", True),
        ("https://bitbucket.org:9000/example/test", "pkg:bitbucket/example/test", True),
        ("http://bitbucket.org/example;key1=1?key2=2#key3=3", "pkg:bitbucket.org/example", True),
    ],
)
def test_compare_purl_and_url(url: str, purl_string: str, expected: bool) -> None:
    """Test comparison of repository type PURLs against matching URLs."""
    purl = PackageURL.from_string(purl_string)
    assert expected == Analyzer.check_if_repository_purl_and_url_match(url, purl)
