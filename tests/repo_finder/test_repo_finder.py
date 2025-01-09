# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the repo finder."""
import os
from pathlib import Path

import pytest
from packageurl import PackageURL
from pytest_httpserver import HTTPServer

from macaron.config.defaults import load_defaults
from macaron.repo_finder import repo_finder
from macaron.repo_finder.repo_finder_enums import RepoFinderOutcome


@pytest.fixture(name="httpserver_java")
def httpserver_java_(tmp_path: Path, httpserver: HTTPServer) -> HTTPServer:
    """Set up the mock HTTP Server for the Repo Finder."""
    url = httpserver.url_for("")
    test_config = f"""
    [repofinder.java]
    artifact_repositories = {url}
    """
    test_config_path = os.path.join(tmp_path, "config.ini")
    with open(test_config_path, "w", encoding="utf-8") as test_config_file:
        test_config_file.write(test_config)
    load_defaults(test_config_path)

    return httpserver


@pytest.mark.parametrize(
    ("test_config", "expected"),
    [
        (
            """
                [repofinder.java]
                repo_pom_paths =
                    scm.connection
                    scm.url
            """,
            "https://github.com/oracle-samples/macaron",
        ),
        (
            """
                [repofinder.java]
                repo_pom_paths =
                    scm.url
                    scm.connection
            """,
            "https://github.com/oracle/macaron",
        ),
    ],
)
def test_pom_extraction_ordering(tmp_path: Path, test_config: str, expected: str, httpserver: HTTPServer) -> None:
    """Test the ordering of elements extracted from the POM is correct and maintained."""
    url = httpserver.url_for("")
    test_config = test_config + f"\nartifact_repositories = {url}"
    test_config_path = os.path.join(tmp_path, "config.ini")
    with open(test_config_path, "w", encoding="utf-8") as test_config_file:
        test_config_file.write(test_config)
    load_defaults(test_config_path)

    pom_text = """
    <project>
        <url>https://example.org</url>
        <scm>
            <connection>scm:git:git@github.com:oracle-samples/macaron.git</connection>
            <url>https://github.com/oracle/macaron</url>
        </scm>
        <properties>
            <url>1.9.15</url>
        </properties>
    </project>
    """

    group = "com.oracle.tools"
    artifact = "oracle-tools-macaron"
    version = "0.4"
    target_url = "/" + "/".join(["/".join(group.split(".")), artifact, version, f"{artifact}-{version}.pom"])
    httpserver.expect_request(target_url).respond_with_data(pom_text)

    found_repo, outcome = repo_finder.find_repo(PackageURL.from_string(f"pkg:maven/{group}/{artifact}@{version}"))
    assert found_repo
    assert found_repo == expected
    assert outcome == RepoFinderOutcome.FOUND


@pytest.mark.parametrize(
    ("test_config", "expected"),
    [
        (
            """
            [repofinder.java]
            artifact_repositories =
                 
            """,
            RepoFinderOutcome.NO_MAVEN_HOST_PROVIDED,
        ),
        (
            """
            [repofinder.java]
            repo_pom_paths =
                 
            """,
            RepoFinderOutcome.NO_POM_TAGS_PROVIDED,
        ),
    ],
)
def test_repo_finder_java_invalid_config(tmp_path: Path, test_config: str, expected: RepoFinderOutcome) -> None:
    """Test the Repo Finder when inputs are invalid: a non-breaking space."""
    test_config_path = os.path.join(tmp_path, "config.ini")
    with open(test_config_path, "w", encoding="utf-8") as test_config_file:
        test_config_file.write(test_config)
    load_defaults(test_config_path)

    found_repo, outcome = repo_finder.find_repo(PackageURL.from_string("pkg:maven/test/test@1"), False)
    assert not found_repo
    assert outcome == expected


@pytest.mark.parametrize(
    ("purl_string", "expected"),
    [
        ("pkg:maven/test/test", RepoFinderOutcome.NO_VERSION_PROVIDED),
        ("pkg:test/test@test", RepoFinderOutcome.UNSUPPORTED_PACKAGE_TYPE),
    ],
)
def test_repo_finder_java_invalid_input(purl_string: str, expected: RepoFinderOutcome) -> None:
    """Test the Repo Finder when invalid input is provided."""
    found_repo, outcome = repo_finder.find_repo(PackageURL.from_string(purl_string), False)
    assert not found_repo
    assert outcome == expected


@pytest.mark.parametrize(
    ("test_pom", "expected"),
    [
        (
            """
            #####<project>
            </project
            """,
            RepoFinderOutcome.POM_READ_ERROR,
        ),
        (
            """
            <project>
                <scm>
                </scm>
            </project>
            """,
            RepoFinderOutcome.SCM_NO_URLS,
        ),
        (
            """
            <project>
                <scm>
                    <url>TEST</url>
                </scm>
            </project>
            """,
            RepoFinderOutcome.SCM_NO_VALID_URLS,
        ),
    ],
)
def test_repo_finder_java_invalid_pom_or_scm(
    httpserver_java: HTTPServer, test_pom: str, expected: RepoFinderOutcome
) -> None:
    """Test the Repo Finder when the POM or SCM metadata is invalid."""
    group = "oracle"
    artifact = "macaron"
    version = "0.3"
    target_url = "/" + "/".join([group, artifact, version, f"{artifact}-{version}.pom"])
    httpserver_java.expect_request(target_url).respond_with_data(test_pom)

    found_repo, outcome = repo_finder.find_repo(
        PackageURL.from_string(f"pkg:maven/{group}/{artifact}@{version}"), False
    )
    assert not found_repo
    assert outcome == expected


def test_repo_finder_java_success(httpserver_java: HTTPServer) -> None:
    """Test the Repo Finder on a repository with a valid POM."""
    pom = """
        <project>
            <scm>
                <url>https://github.com/oracle/macaron</url>
            </scm>
        </project>
        """

    group = "oracle"
    artifact = "macaron"
    version = "0.3"
    target_url = "/" + "/".join([group, artifact, version, f"{artifact}-{version}.pom"])
    httpserver_java.expect_request(target_url).respond_with_data(pom)

    found_repo, outcome = repo_finder.find_repo(PackageURL.from_string(f"pkg:maven/{group}/{artifact}@{version}"))
    assert found_repo
    assert outcome == RepoFinderOutcome.FOUND


def test_repo_finder_java_success_via_parent(httpserver_java: HTTPServer) -> None:
    """Test the Repo Finder on a repository with a valid parent POM."""
    pom = """
        <project>
            <parent>
                <groupId>oracle</groupId>
                <artifactId>macaron</artifactId>
                <version>0.4</version>
            </parent>
        </project>
        """

    parent_pom = """
        <project>
            <scm>
                <url>https://github.com/oracle/macaron</url>
            </scm>
        </project>
        """

    group = "oracle"
    artifact = "macaron"
    version = "0.3"
    target_url = "/" + "/".join([group, artifact, version, f"{artifact}-{version}.pom"])
    httpserver_java.expect_request(target_url).respond_with_data(pom)

    parent_version = "0.4"
    parent_url = "/" + "/".join([group, artifact, parent_version, f"{artifact}-{parent_version}.pom"])
    httpserver_java.expect_request(parent_url).respond_with_data(parent_pom)

    found_repo, outcome = repo_finder.find_repo(PackageURL.from_string(f"pkg:maven/{group}/{artifact}@{version}"))
    assert found_repo
    assert outcome == RepoFinderOutcome.FOUND_FROM_PARENT
