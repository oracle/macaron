# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the deps.dev service."""

import os
import urllib
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Response

from macaron.config.defaults import load_defaults
from macaron.errors import InvalidHTTPResponseError
from macaron.slsa_analyzer.package_registry.deps_dev import DepsDevService


@pytest.mark.parametrize(
    ("purl", "data", "expected"),
    [
        ("pkg%3Apypi%2Fultralytics%408.3.46", "", None),
        ("pkg%3Apypi%2Fultralytics", '{"foo": "bar"}', {"foo": "bar"}),
    ],
)
def test_get_package_info(httpserver: HTTPServer, tmp_path: Path, purl: str, data: str, expected: dict | None) -> None:
    """Test getting package info."""
    base_url_parsed = urllib.parse.urlparse(httpserver.url_for(""))
    user_config_input = f"""
    [deps_dev]
    url_netloc = {base_url_parsed.netloc}
    url_scheme = {base_url_parsed.scheme}
    """

    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)
    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)

    httpserver.expect_request(f"/v3alpha/purl/{purl}").respond_with_response(Response(data))

    assert DepsDevService.get_package_info(purl) == expected


def test_get_package_info_exception(httpserver: HTTPServer, tmp_path: Path) -> None:
    """Test if the function correctly returns an exception."""
    base_url_parsed = urllib.parse.urlparse(httpserver.url_for(""))
    user_config_input = f"""
    [deps_dev]
    url_netloc = {base_url_parsed.netloc}
    url_scheme = {base_url_parsed.scheme}
    """

    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)
    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)

    purl = "pkg%3Apypi%2Fexample"
    httpserver.expect_request(f"/v3alpha/purl/{purl}").respond_with_data("Not Valid")

    with pytest.raises(InvalidHTTPResponseError):
        DepsDevService.get_package_info(purl)
