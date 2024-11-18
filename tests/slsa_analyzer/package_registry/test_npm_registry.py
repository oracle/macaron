# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the npm registry."""

import os
from datetime import datetime
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer

from macaron.config.defaults import load_defaults
from macaron.errors import ConfigurationError, InvalidHTTPResponseError
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.build_tool.npm import NPM
from macaron.slsa_analyzer.package_registry.npm_registry import NPMAttestationAsset, NPMRegistry


@pytest.fixture(name="resources_path")
def resources() -> Path:
    """Create the resources path."""
    return Path(__file__).parent.joinpath("resources")


@pytest.fixture(name="npm_registry")
def create_npm_registry() -> NPMRegistry:
    """Create an npm registry instance."""
    return NPMRegistry(
        hostname="registry.npmjs.org", attestation_endpoint="-/npm/v1/attestations", request_timeout=20, enabled=True
    )


def test_disable_npm_registry(npm_registry: NPMRegistry, tmp_path: Path, npm_tool: NPM) -> None:
    """Test disabling npm registry."""
    config = """
    [package_registry.npm]
    enabled = False
    """
    config_path = os.path.join(tmp_path, "test_config.ini")
    with open(config_path, mode="w", encoding="utf-8") as config_file:
        config_file.write(config)
    load_defaults(config_path)
    npm_registry.load_defaults()

    assert npm_registry.enabled is False
    assert npm_registry.is_detected(build_tool=npm_tool) is False


@pytest.mark.parametrize(
    "config",
    [
        """
            [package_registry.npm]
            hostname =
            """,
        """
            [package_registry.npm]
            attestation_endpoint =
            """,
        """
            [package_registry.npm]
            request_timeout = foo
            """,
    ],
)
def test_npm_registry_invalid_config(npm_registry: NPMRegistry, tmp_path: Path, config: str) -> None:
    """Test loading invalid npm registry configuration."""
    config_path = os.path.join(tmp_path, "test_config.ini")
    with open(config_path, mode="w", encoding="utf-8") as config_file:
        config_file.write(config)
    load_defaults(config_path)
    with pytest.raises(ConfigurationError):
        npm_registry.load_defaults()


@pytest.mark.parametrize(
    (
        "build_tool_name",
        "expected",
    ),
    [
        ("npm", True),
        ("yarn", True),
        ("go", False),
        ("maven", False),
    ],
)
def test_is_detected(
    npm_registry: NPMRegistry, build_tools: dict[str, BaseBuildTool], build_tool_name: str, expected: bool
) -> None:
    """Test that the registry is correctly detected for a build tool."""
    npm_registry.load_defaults()
    assert npm_registry.is_detected(build_tool=build_tools[build_tool_name]) == expected


@pytest.mark.parametrize(
    (
        "namespace",
        "artifact_id",
        "version",
        "expected",
    ),
    [
        (
            "@foo",
            "foo",
            "1.0.0",
            "@foo/foo@1.0.0",
        ),
        (
            None,
            "foo",
            "1.0.0",
            "foo@1.0.0",
        ),
        (
            None,
            "foo",
            "",
            "foo",
        ),
    ],
)
def test_npm_attestation_asset_url(
    npm_registry: NPMRegistry, namespace: str | None, artifact_id: str, version: str, expected: str
) -> None:
    """Test that the npm attestation url is correctly constructed."""
    asset = NPMAttestationAsset(
        namespace=namespace, artifact_id=artifact_id, version=version, npm_registry=npm_registry, size_in_bytes=0
    )
    assert asset.name == artifact_id
    assert asset.url == f"https://{npm_registry.hostname}/{npm_registry.attestation_endpoint}/{expected}"


@pytest.mark.parametrize(
    ("purl", "npm_json_path", "expected_timestamp"),
    [
        (
            "pkg:npm/@sigstore/mock@0.7.5",
            "_sigstore.mock@0.7.5.json",
            "2024-06-11T23:49:17Z",
        ),
    ],
)
def test_find_publish_timestamp(
    resources_path: Path,
    httpserver: HTTPServer,
    purl: str,
    npm_json_path: str,
    expected_timestamp: str,
) -> None:
    """Test that the function finds the timestamp correctly."""
    registry = NPMRegistry()

    with open(os.path.join(resources_path, "npm_registry_files", npm_json_path), encoding="utf8") as page:
        response = page.read()

    httpserver.expect_request(
        "/".join(["/v3alpha", "purl", purl]),
    ).respond_with_data(response)

    publish_time_obj = registry.find_publish_timestamp(purl=purl, registry_url=httpserver.url_for(""))
    expected_time_obj = datetime.strptime(expected_timestamp, "%Y-%m-%dT%H:%M:%S%z")
    assert publish_time_obj == expected_time_obj


@pytest.mark.parametrize(
    ("purl", "npm_json_path", "expected_msg"),
    [
        (
            "pkg:npm/@sigstore/mock@0.7.5",
            "empty_sigstore.mock@0.7.5.json",
            "Invalid response from deps.dev for (.)*",
        ),
        (
            "pkg:npm/@sigstore/mock@0.7.5",
            "invalid_sigstore.mock@0.7.5.json",
            "The timestamp is missing in the response returned by",
        ),
    ],
)
def test_find_publish_timestamp_errors(
    resources_path: Path,
    httpserver: HTTPServer,
    purl: str,
    npm_json_path: str,
    expected_msg: str,
) -> None:
    """Test that the function handles errors correctly."""
    registry = NPMRegistry()

    with open(os.path.join(resources_path, "npm_registry_files", npm_json_path), encoding="utf8") as page:
        response = page.read()

    httpserver.expect_request(
        "/".join(["/v3alpha", "purl", purl]),
    ).respond_with_data(response)

    pat = f"^{expected_msg}"
    with pytest.raises(InvalidHTTPResponseError, match=pat):
        registry.find_publish_timestamp(purl=purl, registry_url=httpserver.url_for(""))
