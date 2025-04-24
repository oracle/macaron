# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the deps.dev service."""

import pytest
from pytest_httpserver import HTTPServer

from macaron.slsa_analyzer.package_registry.deps_dev import APIAccessError, DepsDevService


@pytest.mark.parametrize(
    ("purl", "data", "expected"),
    [
        ("pkg:pypi/ultralytics", '{"foo": "bar"}', {"foo": "bar"}),
    ],
)
def test_get_package_info(
    httpserver: HTTPServer, purl: str, data: str, expected: dict, deps_dev_service_mock: dict
) -> None:
    """Test getting package info."""
    httpserver.expect_request(
        f"/{deps_dev_service_mock['api']}/{deps_dev_service_mock['purl']}/{purl}"
    ).respond_with_data(data)

    assert DepsDevService.get_package_info(purl) == expected


def test_get_package_info_exception(httpserver: HTTPServer, deps_dev_service_mock: dict) -> None:
    """Test if the function correctly returns an exception."""
    purl = "pkg:pypi/example"

    # Return bad JSON data.
    httpserver.expect_request(
        f"/{deps_dev_service_mock['api']}/{deps_dev_service_mock['purl']}/{purl}"
    ).respond_with_data("Not Valid")

    with pytest.raises(APIAccessError, match="^Failed to process"):
        DepsDevService.get_package_info(purl)

    # Request an invalid resource.
    with pytest.raises(APIAccessError, match="^No valid response"):
        DepsDevService.get_package_info("pkg:pypi/test")
