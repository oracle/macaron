# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Module to test the malicious metadata detection check."""

import json
import os
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pytest_httpserver import HTTPServer

from macaron import MACARON_PATH
from macaron.config.defaults import load_defaults
from macaron.malware_analyzer.pypi_heuristics.heuristics import HeuristicResult, Heuristics
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.detect_malicious_metadata_check import DetectMaliciousMetadataCheck
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIRegistry
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo
from tests.conftest import MockAnalyzeContext

RESOURCE_PATH = Path(__file__).parent.joinpath("resources")


@patch("macaron.malware_analyzer.pypi_heuristics.sourcecode.pypi_sourcecode_analyzer.global_config")
@pytest.mark.parametrize(
    ("purl", "expected", "sourcecode_analysis"),
    [
        # TODO: This check is expected to FAIL for pkg:pypi/zlibxjson. However, after introducing the wheel presence
        # heuristic, a false negative has been introduced. Note that if the unit test were allowed to access the OSV
        # knowledge base, it would report the package as malware. However, we intentionally block unit tests
        # from reaching the network.
        pytest.param("pkg:pypi/zlibxjson", CheckResultType.PASSED, False, id="test_malicious_pypi_package"),
        pytest.param("pkg:pypi/test", CheckResultType.UNKNOWN, False, id="test_unknown_pypi_package"),
        pytest.param("pkg:maven:test/test", CheckResultType.UNKNOWN, False, id="test_non_pypi_package"),
        # TODO: including source code analysis that detects flow from a remote point to a file write may assist in resolving
        # the issue of this false negative.
        pytest.param(
            "pkg:pypi/zlibxjson", CheckResultType.PASSED, True, id="test_sourcecode_analysis_malicious_pypi_package"
        ),
    ],
)
def test_detect_malicious_metadata(
    mock_global_config: MagicMock,
    httpserver: HTTPServer,
    tmp_path: Path,
    macaron_path: Path,
    purl: str,
    expected: str,
    sourcecode_analysis: bool,
) -> None:
    """Test that the check handles repositories correctly."""
    check = DetectMaliciousMetadataCheck()

    # Set up the context object with PyPIRegistry instance.
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", purl=purl)
    pypi_registry = PyPIRegistry()
    ctx.dynamic_data["package_registries"] = [PackageRegistryInfo("pip", "pypi", pypi_registry)]
    if sourcecode_analysis:
        ctx.dynamic_data["analyze_source"] = True

    mock_global_config.resources_path = os.path.join(MACARON_PATH, "resources")

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

    [deps_dev]
    url_netloc = {base_url_parsed.netloc}
    url_scheme = {base_url_parsed.scheme}

    [osv_dev]
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


@pytest.mark.parametrize(
    "combination",
    [
        pytest.param(
            {
                # similar to rule ID malware_high_confidence_1, but SUSPICIOUS_SETUP is skipped since the file does not
                # exist, so the rule should not trigger.
                Heuristics.EMPTY_PROJECT_LINK: HeuristicResult.FAIL,
                Heuristics.SOURCE_CODE_REPO: HeuristicResult.SKIP,
                Heuristics.ONE_RELEASE: HeuristicResult.FAIL,
                Heuristics.HIGH_RELEASE_FREQUENCY: HeuristicResult.SKIP,
                Heuristics.UNCHANGED_RELEASE: HeuristicResult.SKIP,
                Heuristics.CLOSER_RELEASE_JOIN_DATE: HeuristicResult.FAIL,
                Heuristics.SUSPICIOUS_SETUP: HeuristicResult.SKIP,
                Heuristics.WHEEL_ABSENCE: HeuristicResult.FAIL,
                Heuristics.ANOMALOUS_VERSION: HeuristicResult.PASS,
            },
            id="test_skipped_evaluation",
        )
    ],
)
def test_evaluations(combination: dict[Heuristics, HeuristicResult]) -> None:
    """Test heuristic combinations to ensure they evaluate as expected."""
    check = DetectMaliciousMetadataCheck()

    confidence, triggered_rules = check.evaluate_heuristic_results(combination)
    assert confidence == 0
    # Expecting this to be a dictionary, so we can ignore the type problems.
    assert len(dict(triggered_rules)) == 0  # type: ignore[arg-type]
