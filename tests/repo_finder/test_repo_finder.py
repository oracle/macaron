# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the repo finder."""

import pytest
from defusedxml.ElementTree import fromstring
from packageurl import PackageURL

from macaron.config.target_config import Configuration
from macaron.repo_finder import repo_validator
from macaron.repo_finder.repo_finder_java import JavaRepoFinder
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


def test_pom_extraction_ordering() -> None:
    """Test the ordering of elements extracted from the POM is correct and maintained."""
    pom_text = """
    <project>
        <url>https://example.org</url>
        <scm>
            <connection>scm:git:git@github.com:oracle-samples/macaron.git</connection>
            <developerConnection>scm:git:git@github.com:oracle/macaron.git</developerConnection>
            <url>https://github.com/oracle/macaron</url>
        </scm>
        <properties>
            <url>1.9.15</url>
        </properties>
    </project>
    """
    pom = fromstring(pom_text)
    repo_finder = JavaRepoFinder()

    # Retrieve SCM from POM.
    connection_urls = repo_finder._find_scm(pom, ["scm.connection", "scm.url"])  # pylint: disable=W0212
    assert connection_urls
    connection_url = repo_validator.find_valid_repository_url(connection_urls)
    assert connection_url

    urls = repo_finder._find_scm(pom, ["scm.url", "scm.connection"])  # pylint: disable=W0212
    assert urls
    url = repo_validator.find_valid_repository_url(urls)
    assert url

    # Ensure found URLs differ.
    assert connection_url != url
