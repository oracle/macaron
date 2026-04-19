# Copyright (c) 2024 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the license check."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from macaron.config.defaults import load_defaults
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.license_check import LicenseCheck
from macaron.slsa_analyzer.git_service.base_git_service import NoneGitService
from macaron.slsa_analyzer.git_service.github import GitHub
from tests.conftest import MockAnalyzeContext


def _make_github_service() -> GitHub:
    """Return a GitHub git service instance with defaults loaded."""
    service = GitHub()
    service.load_defaults()
    return service


def _load_license_config(tmp_path: Path, enabled: bool, allowed: str = "", require: bool = False) -> None:
    """Write a temporary ini file with [license] settings and load it into defaults."""
    config = f"""
[license]
enabled = {enabled}
allowed_licenses =
{chr(10).join("    " + s for s in allowed.splitlines() if s.strip())}
require_license = {require}
"""
    config_path = os.path.join(tmp_path, "license_config.ini")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config)
    load_defaults(config_path)


def test_check_disabled(macaron_path: Path, tmp_path: Path) -> None:
    """Test that the check is skipped when disabled in config."""
    _load_license_config(tmp_path, enabled=False)
    check = LicenseCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    assert check.run_check(ctx).result_type == CheckResultType.SKIPPED


def test_non_github_service(macaron_path: Path, tmp_path: Path) -> None:
    """Test that the check is skipped for non-GitHub repositories."""
    _load_license_config(tmp_path, enabled=True)
    check = LicenseCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.dynamic_data["git_service"] = NoneGitService()
    assert check.run_check(ctx).result_type == CheckResultType.SKIPPED


def test_no_repository(macaron_path: Path, tmp_path: Path) -> None:
    """Test that the check fails when no repository is found."""
    _load_license_config(tmp_path, enabled=True)
    check = LicenseCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.dynamic_data["git_service"] = _make_github_service()
    ctx.component.repository = None  # type: ignore
    assert check.run_check(ctx).result_type == CheckResultType.FAILED


@patch("macaron.slsa_analyzer.git_service.github.GitHub.api_client")
def test_api_allowed_license(mock_api_client: MagicMock, macaron_path: Path, tmp_path: Path) -> None:
    """Test that the check passes when the repository license is in the allow-list."""
    _load_license_config(tmp_path, enabled=True, allowed="MIT\nApache-2.0")
    mock_api_client.get_license.return_value = {
        "license": {"spdx_id": "MIT", "name": "MIT License"},
        "html_url": "https://github.com/owner/repo/blob/main/LICENSE",
    }
    check = LicenseCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.dynamic_data["git_service"] = _make_github_service()
    assert check.run_check(ctx).result_type == CheckResultType.PASSED


@patch("macaron.slsa_analyzer.git_service.github.GitHub.api_client")
def test_api_disallowed_license(mock_api_client: MagicMock, macaron_path: Path, tmp_path: Path) -> None:
    """Test that the check fails when the repository license is not in the allow-list."""
    _load_license_config(tmp_path, enabled=True, allowed="MIT\nApache-2.0")
    mock_api_client.get_license.return_value = {
        "license": {"spdx_id": "GPL-3.0-only", "name": "GNU General Public License v3.0"},
        "html_url": "https://github.com/owner/repo/blob/main/LICENSE",
    }
    check = LicenseCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.dynamic_data["git_service"] = _make_github_service()
    assert check.run_check(ctx).result_type == CheckResultType.FAILED


@patch("macaron.slsa_analyzer.git_service.github.GitHub.api_client")
def test_api_empty_allowlist(mock_api_client: MagicMock, macaron_path: Path, tmp_path: Path) -> None:
    """Test that the check passes for any license when the allow-list is empty."""
    _load_license_config(tmp_path, enabled=True, allowed="")
    mock_api_client.get_license.return_value = {
        "license": {"spdx_id": "Apache-2.0", "name": "Apache License 2.0"},
        "html_url": "https://github.com/owner/repo/blob/main/LICENSE",
    }
    check = LicenseCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.dynamic_data["git_service"] = _make_github_service()
    assert check.run_check(ctx).result_type == CheckResultType.PASSED


@patch("macaron.slsa_analyzer.git_service.github.GitHub.api_client")
def test_api_noassertion_with_filesystem_fallback(
    mock_api_client: MagicMock, macaron_path: Path, tmp_path: Path
) -> None:
    """Test that NOASSERTION triggers filesystem fallback and passes when license file is found."""
    _load_license_config(tmp_path, enabled=True, require=False)
    mock_api_client.get_license.return_value = {
        "license": {"spdx_id": "NOASSERTION"},
    }
    # Create a LICENSE file in tmp_path to simulate the cloned repo.
    license_file = tmp_path / "LICENSE"
    license_file.write_text("MIT License\n", encoding="utf-8")

    check = LicenseCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", fs_path=str(tmp_path))
    ctx.dynamic_data["git_service"] = _make_github_service()
    assert check.run_check(ctx).result_type == CheckResultType.PASSED


@patch("macaron.slsa_analyzer.git_service.github.GitHub.api_client")
def test_no_license_require_true(mock_api_client: MagicMock, macaron_path: Path, tmp_path: Path) -> None:
    """Test that the check fails when no license is found and require_license is True."""
    _load_license_config(tmp_path, enabled=True, require=True)
    mock_api_client.get_license.return_value = {}
    check = LicenseCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", fs_path=str(tmp_path))
    ctx.dynamic_data["git_service"] = _make_github_service()
    assert check.run_check(ctx).result_type == CheckResultType.FAILED


@patch("macaron.slsa_analyzer.git_service.github.GitHub.api_client")
def test_no_license_require_false(mock_api_client: MagicMock, macaron_path: Path, tmp_path: Path) -> None:
    """Test that the check passes when no license is found but require_license is False."""
    _load_license_config(tmp_path, enabled=True, require=False)
    mock_api_client.get_license.return_value = {}
    check = LicenseCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", fs_path=str(tmp_path))
    ctx.dynamic_data["git_service"] = _make_github_service()
    assert check.run_check(ctx).result_type == CheckResultType.PASSED


@patch("macaron.slsa_analyzer.git_service.github.GitHub.api_client")
def test_filesystem_fallback_only(mock_api_client: MagicMock, macaron_path: Path, tmp_path: Path) -> None:
    """Test that the check passes when the API returns nothing but a LICENSE file exists on disk."""
    _load_license_config(tmp_path, enabled=True, require=False)
    mock_api_client.get_license.return_value = {}
    license_file = tmp_path / "LICENSE"
    license_file.write_text("MIT License\n", encoding="utf-8")

    check = LicenseCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", fs_path=str(tmp_path))
    ctx.dynamic_data["git_service"] = _make_github_service()
    assert check.run_check(ctx).result_type == CheckResultType.PASSED
