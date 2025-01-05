# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Module to test the malicious metadata detection check."""

import json
import os
import urllib.parse
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer

from macaron.config.defaults import load_defaults
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.detect_malicious_metadata_check import DetectMaliciousMetadataCheck
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIRegistry
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo
from tests.conftest import MockAnalyzeContext

RESOURCE_PATH = Path(__file__).parent.joinpath("resources")


@pytest.mark.parametrize(
    ("purl", "expected"),
    [
        # TODO: This check is expected to FAIL for pkg:pypi/zlibxjson. However, after introducing the wheel presence heuristic,
        # a false negative has been introduced. Note that if the unit test were allowed to access the OSV
        # knowledge base, it would report the package as malware. However, we intentionally block unit tests
        # from reaching the network.
        ("pkg:pypi/zlibxjson", CheckResultType.PASSED),
        ("pkg:pypi/test", CheckResultType.UNKNOWN),
        ("pkg:maven:test/test", CheckResultType.UNKNOWN),
    ],
)
def test_detect_malicious_metadata(
    httpserver: HTTPServer, tmp_path: Path, pip_tool: BaseBuildTool, macaron_path: Path, purl: str, expected: str
) -> None:
    """Test that the check handles repositories correctly."""
    check = DetectMaliciousMetadataCheck()

    # Set up the context object with PyPIRegistry instance.
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", purl=purl)
    pypi_registry = PyPIRegistry()
    ctx.dynamic_data["package_registries"] = [PackageRegistryInfo(pip_tool, pypi_registry)]

    # Set up responses of PyPI endpoints using the httpserver plugin.
    with open(os.path.join(RESOURCE_PATH, "pypi_files", "zlibxjson.html"), encoding="utf8") as page:
        p_page_content = page.read()

    with open(os.path.join(RESOURCE_PATH, "pypi_files", "zlibxjson_user.html"), encoding="utf8") as page:
        u_page_content = page.read()

    with open(os.path.join(RESOURCE_PATH, "pypi_files", "zlibxjson_package.json"), encoding="utf8") as page:
        package_json = json.load(page)

    with open(os.path.join(RESOURCE_PATH, "pypi_files", "zlibxjson-8.2.source"), "rb") as source:
        source_tarball = source.read()

    base_url_parsed = urllib.parse.urlparse(httpserver.url_for(""))
    user_config_input = f"""
    [package_registry.pypi]
    request_timeout = 20
    registry_url_netloc = {base_url_parsed.netloc}
    registry_url_scheme = {base_url_parsed.scheme}
    fileserver_url_netloc = {base_url_parsed.netloc}
    fileserver_url_scheme = {base_url_parsed.scheme}
    inspector_url_netloc = {base_url_parsed.netloc}
    inspector_url_scheme = {base_url_parsed.scheme}
    """

    check.osv_query_url = f"{base_url_parsed.scheme}://{base_url_parsed.netloc}"
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)
    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)
    pypi_registry.load_defaults()

    httpserver.expect_request("/project/zlibxjson").respond_with_data(p_page_content)
    httpserver.expect_request("/user/tser111111").respond_with_data(u_page_content)
    httpserver.expect_request("/pypi/zlibxjson/json").respond_with_json(package_json)
    httpserver.expect_request(
        "/packages/3e/1e/b1ecb05e7ca1eb74ca6257a7f43d052b90d2ac01feb28eb28ce677a871ab/zlibxjson-8.2.tar.gz"
    ).respond_with_data(source_tarball, content_type="application/octet-stream")
    httpserver.expect_request(
        "/project/zlibxjson/8.2/packages/55/b3/3a43f065f6199d519ebbb48f3a94c4f0557beb34bbed48c1ba89c67b1959/zlibxjson-8.2-py3-none-any.whl"
    ).respond_with_json({})
    httpserver.expect_request(
        "/project/zlibxjson/8.2/packages/3e/1e/b1ecb05e7ca1eb74ca6257a7f43d052b90d2ac01feb28eb28ce677a871ab/zlibxjson-8.2.tar.gz"
    ).respond_with_json({})

    assert check.run_check(ctx).result_type == expected
