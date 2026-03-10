# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the osv.dev service."""

import os
from pathlib import Path

import pytest

from macaron.config.defaults import load_defaults
from macaron.errors import APIAccessError
from macaron.slsa_analyzer.package_registry.osv_dev import OSVDevService


@pytest.mark.parametrize(
    ("user_config_input"),
    [
        pytest.param(
            """
            [osv_dev]
            url_netloc =
            url_scheme = https
            query_endpoint = v1/query
            """,
            id="Missing netloc",
        ),
        pytest.param(
            """
            [osv_dev]
            url_netloc = osv.dev
            url_scheme = https
            query_endpoint =
            """,
            id="Missing query endpoint",
        ),
    ],
)
def test_load_defaults_query_api(tmp_path: Path, user_config_input: str) -> None:
    """Test the ``load_defaults`` method."""
    user_config_path = os.path.join(tmp_path, "config.ini")

    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)

    # We don't have to worry about modifying the ``defaults`` object causing test
    # pollution here, since we reload the ``defaults`` object before every test with the
    # ``setup_test`` fixture.
    load_defaults(user_config_path)

    with pytest.raises(APIAccessError):
        OSVDevService.call_osv_query_api({})


def test_is_affected_version_invalid_commit() -> None:
    """Test if the function can handle invalid commits"""
    with pytest.raises(APIAccessError, match="^Failed to find a tag for"):
        OSVDevService.is_version_affected(
            vuln={},
            pkg_name="pkg",
            pkg_version="c253e1f19ebfb98fe02a8354082cbbd282d446a0",
            ecosystem="GitHub Actions",
            source_repo="mock_repo",
        )


def test_is_affected_version_invalid_response() -> None:
    """Test if the function can handle empty OSV response."""
    with pytest.raises(APIAccessError, match="^Received invalid response for"):
        OSVDevService.is_version_affected(
            vuln={"vulns": []}, pkg_name="repo/workflow", pkg_version="1.0.0", ecosystem="GitHub Actions"
        )


@pytest.mark.parametrize(
    ("vuln", "workflow"),
    [
        pytest.param(
            {
                "id": "GHSA-mrrh-fwg8-r2c3",
                "affected": [
                    {
                        "package": {"name": "tj-actions/changed-files", "ecosystem": "GitHub Actions"},
                    }
                ],
            },
            "tj-actions/changed-files",
            id="Test missing ranges",
        ),
        pytest.param(
            {
                "id": "GHSA-mrrh-fwg8-r2c3",
                "affected": [
                    {
                        "package": {"name": "tj-actions/changed-files", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {
                                "type": "ECOSYSTEM",
                            }
                        ],
                    }
                ],
            },
            "tj-actions/changed-files",
            id="Test missing events",
        ),
    ],
)
def test_is_affected_version_invalid_osv_vulns(vuln: dict, workflow: str) -> None:
    """Test if the function can handle invalid OSV vulnerability data."""
    with pytest.raises(APIAccessError):
        OSVDevService.is_version_affected(
            vuln=vuln, pkg_name=workflow, pkg_version="45.0.0", ecosystem="GitHub Actions"
        )


@pytest.mark.parametrize(
    ("vuln", "workflow", "version", "expected"),
    [
        pytest.param(
            {
                "id": "GHSA-mrrh-fwg8-r2c3",
                "affected": [
                    {
                        "package": {"name": "tj-actions/changed-files", "ecosystem": "GitHub Actions"},
                        "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "46.0.1"}]}],
                    }
                ],
            },
            "tj-actions/changed-files",
            "45.0.0",
            True,
            id="Test affected version",
        ),
        pytest.param(
            {
                "id": "GHSA-mrrh-fwg8-r2c3",
                "affected": [
                    {
                        "package": {"name": "tj-actions/changed-files", "ecosystem": "GitHub Actions"},
                        "ranges": [{"type": "ECOSYSTEM", "events": [{"fixed": "46.0.1"}]}],
                    }
                ],
            },
            "tj-actions/changed-files",
            "45.0.0",
            True,
            id="Test affected version missing introduced",
        ),
        pytest.param(
            {
                "id": "GHSA-mrrh-fwg8-r2c3",
                "affected": [
                    {
                        "package": {"name": "tj-actions/changed-files", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {
                                "type": "ECOSYSTEM",
                                "events": [
                                    {"introduced": "0"},
                                ],
                            }
                        ],
                    }
                ],
            },
            "tj-actions/changed-files",
            "45.0.0",
            True,
            id="Test affected version missing fix",
        ),
        pytest.param(
            {
                "id": "GHSA-mrrh-fwg8-r2c3",
                "affected": [
                    {
                        "package": {"name": "tj-actions/changed-files", "ecosystem": "GitHub Actions"},
                        "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "46.0.1"}]}],
                    }
                ],
            },
            "tj-actions/changed-files",
            "47.0.0",
            False,
            id="Test unaffected version",
        ),
        pytest.param(
            {
                "id": "GHSA-mrrh-fwg8-r2c3",
                "affected": [
                    {
                        "package": {"name": "tj-actions/changed-files", "ecosystem": "GitHub Actions"},
                        "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "1.0.0"}, {"fixed": "46.0.1"}]}],
                    }
                ],
            },
            "tj-actions/changed-files",
            "1.0.0",
            True,
            id="Test introduced version",
        ),
        pytest.param(
            {
                "id": "GHSA-mrrh-fwg8-r2c3",
                "affected": [
                    {
                        "package": {"name": "tj-actions/changed-files", "ecosystem": "GitHub Actions"},
                        "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "46.0.1"}]}],
                    }
                ],
            },
            "tj-actions/changed-files",
            "46.0.1",
            False,
            id="Test fix version",
        ),
    ],
)
def test_is_affected_version_ranges(vuln: dict, workflow: str, version: str, expected: bool) -> None:
    """Test if the function can handle corner cases."""
    assert (
        OSVDevService.is_version_affected(vuln=vuln, pkg_name=workflow, pkg_version=version, ecosystem="GitHub Actions")
        == expected
    )


@pytest.mark.parametrize(
    ("packages", "osv_batch_response", "expected"),
    [
        pytest.param(
            [{"package": {"ecosystem": "GitHub Actions", "name": "aquasecurity/trivy-action"}}],
            {
                "results": [
                    {
                        "vulns": [
                            {"id": "GHSA-69fq-xp46-6x23", "modified": "2026-03-24T18:02:32.837793Z"},
                            {"id": "GHSA-9p44-j4g5-cfx5", "modified": "2026-02-22T23:23:29.929429Z"},
                        ]
                    }
                ]
            },
            [{"package": {"ecosystem": "GitHub Actions", "name": "aquasecurity/trivy-action"}}],
            id="Single vulnerable package",
        ),
        pytest.param(
            [{"package": {"ecosystem": "GitHub Actions", "name": ""}}],
            {"results": [{}]},
            [],
            id="Empty package name",
        ),
    ],
)
def test_get_vulnerabilities_package_name_batch(
    monkeypatch: pytest.MonkeyPatch, packages: list, osv_batch_response: dict[str, list], expected: list
) -> None:
    """Test filtering vulnerable packages from OSV batch query results."""

    def mock_call_osv_querybatch_api(query_data: dict, expected_size: int | None = None) -> list:
        assert query_data == {"queries": packages}
        assert query_data["queries"][0]["package"]["name"] == packages[0]["package"]["name"]
        assert expected_size == len(packages)
        return osv_batch_response["results"]

    monkeypatch.setattr(OSVDevService, "call_osv_querybatch_api", staticmethod(mock_call_osv_querybatch_api))

    assert OSVDevService.get_vulnerabilities_package_name_batch(packages) == expected
