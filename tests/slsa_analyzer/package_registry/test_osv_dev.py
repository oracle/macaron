# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the osv.dev service."""

import os
from pathlib import Path

import pytest
from packaging.version import Version

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
    """Test if the function can handle invalid commits."""
    with pytest.raises(APIAccessError, match=r"^Failed to find a tag for"):
        OSVDevService.is_version_affected(
            vuln={},
            pkg_name="pkg",
            pkg_version="c253e1f19ebfb98fe02a8354082cbbd282d446a0",
            ecosystem="GitHub Actions",
            source_repo="mock_repo",
        )


def test_is_affected_version_invalid_response() -> None:
    """Test if the function can handle empty OSV response."""
    with pytest.raises(APIAccessError, match=r"^Received invalid response for"):
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
        pytest.param(
            {
                "id": "GHSA-6f4g-xm8v-pgv6",
                "affected": [
                    {
                        "package": {"name": "tmatens/compose-lint", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {
                                "type": "GIT",
                                "repo": "https://github.com/tmatens/compose-lint",
                                "events": [
                                    {"introduced": "60c091c7cc8f86c6b0c5954031097364fea0a201"},
                                    {"fixed": "a6a7a76736de1c72abfa96c41ff8af556ffdc55f"},
                                ],
                            },
                        ],
                    }
                ],
            },
            "tmatens/compose-lint",
            id="Test only GIT ranges",
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
        pytest.param(
            {
                "id": "GHSA-5xjx-3w67-w9x9",
                "affected": [
                    {
                        "package": {"name": "pypa/gh-action-pypi-publish", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.14.3"}]},
                            {
                                "type": "GIT",
                                "repo": "https://github.com/pypa/gh-action-pypi-publish",
                                "events": [{"introduced": "0"}, {"fixed": "7245906fb61fa33a13554f9d5fb856fe61758086"}],
                            },
                        ],
                    }
                ],
            },
            "pypa/gh-action-pypi-publish",
            "v1.14.3",
            False,
            id="Test fixed version with a GIT range",
        ),
        pytest.param(
            {
                "id": "GHSA-5xjx-3w67-w9x9",
                "affected": [
                    {
                        "package": {"name": "pypa/gh-action-pypi-publish", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.14.3"}]},
                            {
                                "type": "GIT",
                                "repo": "https://github.com/pypa/gh-action-pypi-publish",
                                "events": [{"introduced": "0"}, {"fixed": "7245906fb61fa33a13554f9d5fb856fe61758086"}],
                            },
                        ],
                    }
                ],
            },
            "pypa/gh-action-pypi-publish",
            "v1.14.2",
            True,
            id="Test affected version with a GIT range",
        ),
        pytest.param(
            {
                "id": "GHSA-6f4g-xm8v-pgv6",
                "affected": [
                    {
                        "package": {"name": "tmatens/compose-lint", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {"type": "ECOSYSTEM", "events": [{"introduced": "0.2.0"}, {"fixed": "0.31.0"}]},
                            {
                                "type": "GIT",
                                "repo": "https://github.com/tmatens/compose-lint",
                                "events": [
                                    {"introduced": "60c091c7cc8f86c6b0c5954031097364fea0a201"},
                                    {"fixed": "a6a7a76736de1c72abfa96c41ff8af556ffdc55f"},
                                ],
                            },
                        ],
                    }
                ],
            },
            "tmatens/compose-lint",
            "0.1.0",
            False,
            id="Test version before introduced with a GIT range",
        ),
        pytest.param(
            {
                "id": "GHSA-6f4g-xm8v-pgv6",
                "affected": [
                    {
                        "package": {"name": "tmatens/compose-lint", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {"type": "ECOSYSTEM", "events": [{"introduced": "0.2.0"}, {"fixed": "0.31.0"}]},
                            {
                                "type": "GIT",
                                "repo": "https://github.com/tmatens/compose-lint",
                                "events": [
                                    {"introduced": "60c091c7cc8f86c6b0c5954031097364fea0a201"},
                                    {"fixed": "a6a7a76736de1c72abfa96c41ff8af556ffdc55f"},
                                ],
                            },
                        ],
                    }
                ],
            },
            "tmatens/compose-lint",
            "0.31.0",
            False,
            id="Test fix version with a GIT range",
        ),
        pytest.param(
            {
                "id": "GHSA-r4fj-r33x-8v88",
                "affected": [
                    {
                        "package": {"name": "njzjz/wenxian", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"last_affected": "0.3.1"}]},
                        ],
                    }
                ],
            },
            "njzjz/wenxian",
            "0.3.1",
            True,
            id="Test last_affected version",
        ),
        pytest.param(
            {
                "id": "GHSA-r4fj-r33x-8v88",
                "affected": [
                    {
                        "package": {"name": "njzjz/wenxian", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"last_affected": "0.3.1"}]},
                        ],
                    }
                ],
            },
            "njzjz/wenxian",
            "0.3.2",
            False,
            id="Test version after last_affected",
        ),
        pytest.param(
            {
                "id": "GHSA-test-multiple-intervals",
                "affected": [
                    {
                        "package": {"name": "rlespinasse/github-slug-action", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {
                                "type": "ECOSYSTEM",
                                "events": [
                                    {"introduced": "0"},
                                    {"fixed": "1.1.1"},
                                    {"introduced": "2.0.0"},
                                    {"fixed": "2.1.1"},
                                ],
                            },
                        ],
                    }
                ],
            },
            "rlespinasse/github-slug-action",
            "1.0.0",
            True,
            id="Test version in the first interval",
        ),
        pytest.param(
            {
                "id": "GHSA-test-multiple-intervals",
                "affected": [
                    {
                        "package": {"name": "rlespinasse/github-slug-action", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {
                                "type": "ECOSYSTEM",
                                "events": [
                                    {"introduced": "0"},
                                    {"fixed": "1.1.1"},
                                    {"introduced": "2.0.0"},
                                    {"fixed": "2.1.1"},
                                ],
                            },
                        ],
                    }
                ],
            },
            "rlespinasse/github-slug-action",
            "1.2.0",
            False,
            id="Test version between two intervals",
        ),
        pytest.param(
            {
                "id": "GHSA-test-multiple-intervals",
                "affected": [
                    {
                        "package": {"name": "rlespinasse/github-slug-action", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {
                                "type": "ECOSYSTEM",
                                "events": [
                                    {"introduced": "0"},
                                    {"fixed": "1.1.1"},
                                    {"introduced": "2.0.0"},
                                    {"fixed": "2.1.1"},
                                ],
                            },
                        ],
                    }
                ],
            },
            "rlespinasse/github-slug-action",
            "2.0.0",
            True,
            id="Test version in the second interval",
        ),
        pytest.param(
            {
                "id": "GHSA-test-multiple-intervals",
                "affected": [
                    {
                        "package": {"name": "rlespinasse/github-slug-action", "ecosystem": "GitHub Actions"},
                        "ranges": [
                            {
                                "type": "ECOSYSTEM",
                                "events": [
                                    {"introduced": "0"},
                                    {"fixed": "1.1.1"},
                                    {"introduced": "2.0.0"},
                                    {"fixed": "2.1.1"},
                                ],
                            },
                        ],
                    }
                ],
            },
            "rlespinasse/github-slug-action",
            "2.1.1",
            False,
            id="Test fix version of the second interval",
        ),
    ],
)
def test_is_affected_version_ranges(vuln: dict, workflow: str, version: str, expected: bool) -> None:
    """Test if the function can handle corner cases."""
    assert (
        OSVDevService.is_version_affected(vuln=vuln, pkg_name=workflow, pkg_version=version, ecosystem="GitHub Actions")
        == expected
    )


UNSORTED_EVENTS_CASES = [
    pytest.param(
        [{"fixed": "1.0.0"}, {"introduced": "0"}],
        {"0.9.0": True, "1.0.0": False, "2.0.0": False},
        id="fixed before introduced",
    ),
    pytest.param(
        [{"last_affected": "1.0.0"}, {"introduced": "0"}],
        {"0.9.0": True, "1.0.0": True, "1.0.1": False},
        id="last_affected before introduced",
    ),
    pytest.param(
        [{"fixed": "3.0.0"}, {"introduced": "0"}, {"introduced": "2.0.0"}, {"fixed": "1.0.0"}],
        {
            "0.5.0": True,
            "2.0.0": True,
            "2.5.0": True,
            "1.0.0": False,
            "1.5.0": False,
            "3.0.0": False,
            "3.5.0": False,
        },
        id="multiple intervals shuffled",
    ),
]


def _sorted_events(events: list[dict]) -> list[dict]:
    """Return the events in chronological (version) order, with "introduced": "0" first."""

    def key(event: dict) -> tuple[bool, Version]:
        value = next(iter(event.values()))
        return (value != "0", Version(value))

    return sorted(events, key=key)


@pytest.mark.parametrize("ordered", [False, True], ids=["unsorted", "sorted"])
@pytest.mark.parametrize(("events", "expected"), UNSORTED_EVENTS_CASES)
def test_is_affected_version_event_order(events: list[dict], expected: dict[str, bool], ordered: bool) -> None:
    """Test that the order of the events in a range does not change the result."""
    if ordered:
        events = _sorted_events(events)
    vuln = {
        "id": "GHSA-test-event-order",
        "affected": [
            {
                "package": {"name": "rlespinasse/github-slug-action", "ecosystem": "GitHub Actions"},
                "ranges": [{"type": "ECOSYSTEM", "events": events}],
            }
        ],
    }
    for pkg_version, affected in expected.items():
        assert (
            OSVDevService.is_version_affected(
                vuln=vuln,
                pkg_name="rlespinasse/github-slug-action",
                pkg_version=pkg_version,
                ecosystem="GitHub Actions",
            )
            == affected
        ), pkg_version


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
