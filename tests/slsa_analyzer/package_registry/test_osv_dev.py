# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
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
    with pytest.raises(APIAccessError):
        OSVDevService.is_version_affected(
            vuln={}, pkg_name="pkg", pkg_version="invalid_commit", ecosystem="GitHub Actions"
        )


def test_is_affected_version_invalid_response() -> None:
    """Test if the function can handle empty OSV response."""
    with pytest.raises(APIAccessError):
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
