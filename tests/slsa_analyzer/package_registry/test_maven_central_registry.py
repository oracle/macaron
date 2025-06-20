# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the Maven Central registry."""

import json
import os
import urllib.parse
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import pytest
from packageurl import PackageURL
from pytest_httpserver import HTTPServer

from macaron.artifact.maven import construct_maven_repository_path, construct_primary_jar_file_name
from macaron.config.defaults import load_defaults
from macaron.errors import ConfigurationError, InvalidHTTPResponseError
from macaron.slsa_analyzer.package_registry.maven_central_registry import MavenCentralRegistry


@pytest.fixture(name="resources_path")
def resources() -> Path:
    """Create the resources path."""
    return Path(__file__).parent.joinpath("resources")


@pytest.fixture(name="maven_central")
def maven_central_instance() -> MavenCentralRegistry:
    """Create a ``MavenCentralRegistry`` object for the following tests."""
    return MavenCentralRegistry(
        search_netloc="search.maven.org",
        search_scheme="https",
        search_endpoint="solrsearch/select",
        registry_url_netloc="repo1.maven.org/maven2",
        registry_url_scheme="https",
    )


@pytest.fixture(name="maven_service")
def maven_service_(httpserver: HTTPServer, tmp_path: Path) -> None:
    """Set up the Maven httpserver."""
    base_url_parsed = urllib.parse.urlparse(httpserver.url_for(""))

    user_config_input = f"""
    [package_registry.maven_central]
    request_timeout = 20
    search_netloc = {base_url_parsed.netloc}
    search_scheme = {base_url_parsed.scheme}
    registry_url_netloc = {base_url_parsed.netloc}
    registry_url_scheme = {base_url_parsed.scheme}
    """
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)
    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)


def test_load_defaults(tmp_path: Path) -> None:
    """Test the ``load_defaults`` method."""
    user_config_path = os.path.join(tmp_path, "config.ini")
    user_config_input = """
        [package_registry.maven_central]
        search_netloc = search.maven.test
        search_scheme = http
        search_endpoint = test
        registry_url_netloc = test.repo1.maven.org/maven2
        registry_url_scheme = http
        request_timeout = 5
    """
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)

    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)

    maven_central = MavenCentralRegistry()
    maven_central.load_defaults()
    assert maven_central.search_netloc == "search.maven.test"
    assert maven_central.search_scheme == "http"
    assert maven_central.search_endpoint == "test"
    assert maven_central.registry_url_netloc == "test.repo1.maven.org/maven2"
    assert maven_central.registry_url_scheme == "http"


def test_load_defaults_without_maven_central_config() -> None:
    """Test the ``load_defaults`` method in trivial case when no config is given."""
    maven_central = MavenCentralRegistry()
    maven_central.load_defaults()


@pytest.mark.parametrize(
    ("user_config_input"),
    [
        pytest.param(
            """
            [package_registry.maven_central]
            search_netloc =
            """,
            id="Missing search netloc",
        ),
        pytest.param(
            """
            [package_registry.maven_central]
            search_endpoint =
            """,
            id="Missing search endpoint",
        ),
        pytest.param(
            """
            [package_registry.maven_central]
            request_timeout = foo
            """,
            id="Invalid value for request_timeout",
        ),
    ],
)
def test_load_defaults_with_invalid_config(tmp_path: Path, user_config_input: str) -> None:
    """Test the ``load_defaults`` method in case the config is invalid."""
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)

    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)

    maven_central = MavenCentralRegistry()
    with pytest.raises(ConfigurationError):
        maven_central.load_defaults()


@pytest.mark.parametrize(
    ("build_tool_name", "expected_result"),
    [
        ("maven", True),
        ("gradle", True),
        ("pip", False),
        ("poetry", False),
    ],
)
def test_is_detected(
    maven_central: MavenCentralRegistry,
    build_tool_name: str,
    expected_result: bool,
) -> None:
    """Test the ``is_detected`` method."""
    assert maven_central.is_detected(build_tool_name) == expected_result


@pytest.mark.parametrize(
    ("purl", "mc_json_path", "query_string", "expected_timestamp"),
    [
        (
            "pkg:maven/org.apache.logging.log4j/log4j-core@3.0.0-beta2",
            "log4j-core@3.0.0-beta2-select.json",
            "q=g:org.apache.logging.log4j+AND+a:log4j-core+AND+v:3.0.0-beta2&core=gav&rows=1&wt=json",
            "2024-02-17T18:50:09+00:00",
        ),
        (
            "pkg:maven/com.fasterxml.jackson.core/jackson-annotations@2.16.1",
            "jackson-annotations@2.16.1-select.json",
            "q=g:com.fasterxml.jackson.core+AND+a:jackson-annotations+AND+v:2.16.1&core=gav&rows=1&wt=json",
            "2023-12-24T04:02:40+00:00",
        ),
    ],
)
def test_find_publish_timestamp(
    resources_path: Path,
    httpserver: HTTPServer,
    maven_service: dict,  # pylint: disable=unused-argument
    purl: str,
    mc_json_path: str,
    query_string: str,
    expected_timestamp: str,
) -> None:
    """Test that the function finds the timestamp correctly."""
    maven_central = MavenCentralRegistry()
    maven_central.load_defaults()

    with open(os.path.join(resources_path, "maven_central_files", mc_json_path), encoding="utf8") as page:
        mc_json_response = json.load(page)

    httpserver.expect_request(
        "/solrsearch/select",
        query_string=query_string,
    ).respond_with_json(mc_json_response)

    publish_time_obj = maven_central.find_publish_timestamp(purl=purl)
    expected_time_obj = datetime.strptime(expected_timestamp, "%Y-%m-%dT%H:%M:%S%z")
    assert publish_time_obj == expected_time_obj


@pytest.mark.parametrize(
    ("purl", "mc_json_path", "expected_msg"),
    [
        (
            "pkg:maven/org.apache.logging.log4j/log4j-core@3.0.0-beta2",
            "empty_log4j-core@3.0.0-beta2-select.json",
            "Empty response returned by (.)*",
        ),
        (
            "pkg:maven/org.apache.logging.log4j/log4j-core@3.0.0-beta2",
            "invalid_log4j-core@3.0.0-beta2-select.json",
            "The response returned by (.)* misses `response.docs` attribute or it is empty",
        ),
    ],
)
def test_find_publish_timestamp_errors(
    resources_path: Path,
    httpserver: HTTPServer,
    maven_service: dict,  # pylint: disable=unused-argument
    purl: str,
    mc_json_path: str,
    expected_msg: str,
) -> None:
    """Test that the function handles errors correctly."""
    maven_central = MavenCentralRegistry()
    maven_central.load_defaults()

    with open(os.path.join(resources_path, "maven_central_files", mc_json_path), encoding="utf8") as page:
        mc_json_response = json.load(page)

    # Set up responses of solrsearch endpoints using the httpserver plugin.
    httpserver.expect_request(
        "/solrsearch/select",
        query_string="q=g:org.apache.logging.log4j+AND+a:log4j-core+AND+v:3.0.0-beta2&core=gav&rows=1&wt=json",
    ).respond_with_json(mc_json_response)

    pat = f"^{expected_msg}"
    with pytest.raises(InvalidHTTPResponseError, match=pat):
        maven_central.find_publish_timestamp(purl=purl)


@pytest.mark.parametrize("purl_string", ["pkg:maven/example", "pkg:maven/example/test", "pkg:maven/example/test@1"])
def test_get_artifact_hash_failures(
    httpserver: HTTPServer, maven_service: dict, purl_string: str  # pylint: disable=unused-argument
) -> None:
    """Test failures of get artifact hash."""
    purl = PackageURL.from_string(purl_string)

    maven_registry = MavenCentralRegistry()
    maven_registry.load_defaults()

    if purl.namespace and purl.version and (file_name := construct_primary_jar_file_name(purl)) and file_name:
        artifact_path = "/" + construct_maven_repository_path(purl.namespace, purl.name, purl.version) + "/" + file_name
        hash_algorithm = sha256()
        hash_algorithm.update(b"example_data")
        expected_hash = hash_algorithm.hexdigest()
        httpserver.expect_request(artifact_path + ".sha256").respond_with_data(expected_hash)
        httpserver.expect_request(artifact_path).respond_with_data(b"example_data_2")

    result = maven_registry.get_artifact_hash(purl)

    assert not result


def test_get_artifact_hash_success(
    httpserver: HTTPServer, maven_service: dict  # pylint: disable=unused-argument
) -> None:
    """Test success of get artifact hash."""
    purl = PackageURL.from_string("pkg:maven/example/test@1")
    assert purl.namespace
    assert purl.version

    maven_registry = MavenCentralRegistry()
    maven_registry.load_defaults()

    file_name = construct_primary_jar_file_name(purl)
    assert file_name

    artifact_path = "/" + construct_maven_repository_path(purl.namespace, purl.name, purl.version) + "/" + file_name
    hash_algorithm = sha256()
    hash_algorithm.update(b"example_data")
    expected_hash = hash_algorithm.hexdigest()
    httpserver.expect_request(artifact_path + ".sha256").respond_with_data(expected_hash)
    httpserver.expect_request(artifact_path).respond_with_data(b"example_data")

    result = maven_registry.get_artifact_hash(purl)

    assert result
