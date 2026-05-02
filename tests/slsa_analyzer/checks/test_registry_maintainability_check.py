# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the registry maintainability check."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from macaron.config.defaults import load_defaults
from macaron.errors import InvalidHTTPResponseError
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.registry_maintainability_check import RegistryMaintainabilityCheck
from macaron.slsa_analyzer.git_service.base_git_service import NoneGitService
from macaron.slsa_analyzer.git_service.github import GitHub
from macaron.slsa_analyzer.package_registry.npm_registry import NPMRegistry
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIRegistry
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo
from tests.conftest import MockAnalyzeContext

_PYPI_PURL = "pkg:pypi/requests@2.28.0"
_NPM_PURL = "pkg:npm/express@4.18.2"
_NO_VERSION_PURL = "pkg:pypi/requests"


def _make_github_service() -> GitHub:
    """Return a GitHub git service instance with defaults loaded."""
    service = GitHub()
    service.load_defaults()
    return service


def _load_registry_config(tmp_path: Path, threshold_days: int = 365) -> None:
    """Write a temporary ini file with [registry_maintainability] settings and load it."""
    config = f"""
[registry_maintainability]
inactivity_threshold_days = {threshold_days}
"""
    config_path = os.path.join(tmp_path, "registry_config.ini")
    with open(config_path, "w", encoding="utf-8") as fh:
        fh.write(config)
    load_defaults(config_path)


def _make_pypi_registry_info() -> PackageRegistryInfo:
    """Build a minimal PyPI PackageRegistryInfo suitable for tests."""
    pypi_registry = PyPIRegistry()
    pypi_registry.load_defaults()
    return PackageRegistryInfo(ecosystem="pypi", package_registry=pypi_registry)


def _mock_pypi_ctx(macaron_path: Path, purl: str = _PYPI_PURL) -> MockAnalyzeContext:
    """Return a MockAnalyzeContext wired up with a PyPI registry."""
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", purl=purl)
    ctx.dynamic_data["package_registries"] = [_make_pypi_registry_info()]
    ctx.dynamic_data["git_service"] = NoneGitService()
    return ctx

# Tests


def test_unknown_no_version(macaron_path: Path, tmp_path: Path) -> None:
    """The check returns UNKNOWN when the PURL has no version pinned."""
    _load_registry_config(tmp_path)
    check = RegistryMaintainabilityCheck()
    ctx = _mock_pypi_ctx(macaron_path, purl=_NO_VERSION_PURL)
    assert check.run_check(ctx).result_type == CheckResultType.UNKNOWN


def test_unknown_no_registries(macaron_path: Path, tmp_path: Path) -> None:
    """The check returns UNKNOWN when no package registries are matched."""
    _load_registry_config(tmp_path)
    check = RegistryMaintainabilityCheck()
    ctx = _mock_pypi_ctx(macaron_path)
    ctx.dynamic_data["package_registries"] = []
    assert check.run_check(ctx).result_type == CheckResultType.UNKNOWN


@patch(
    "macaron.slsa_analyzer.package_registry.package_registry.PackageRegistry.find_publish_timestamp"
)
def test_unknown_api_error(
    mock_timestamp: MagicMock, macaron_path: Path, tmp_path: Path
) -> None:
    """The check returns UNKNOWN when deps.dev raises InvalidHTTPResponseError."""
    _load_registry_config(tmp_path)
    mock_timestamp.side_effect = InvalidHTTPResponseError("API unavailable")
    check = RegistryMaintainabilityCheck()
    ctx = _mock_pypi_ctx(macaron_path)
    assert check.run_check(ctx).result_type == CheckResultType.UNKNOWN


@patch(
    "macaron.slsa_analyzer.package_registry.package_registry.PackageRegistry.find_publish_timestamp"
)
@patch("macaron.slsa_analyzer.checks.registry_maintainability_check._check_deprecated")
def test_pass_recent_release(
    mock_deprecated: MagicMock,
    mock_timestamp: MagicMock,
    macaron_path: Path,
    tmp_path: Path,
) -> None:
    """The check passes when the last release is within the threshold."""
    _load_registry_config(tmp_path, threshold_days=365)
    recent = datetime.now(timezone.utc) - timedelta(days=30)
    mock_timestamp.return_value = recent
    mock_deprecated.return_value = (False, None)

    check = RegistryMaintainabilityCheck()
    ctx = _mock_pypi_ctx(macaron_path)
    assert check.run_check(ctx).result_type == CheckResultType.PASSED


@patch(
    "macaron.slsa_analyzer.package_registry.package_registry.PackageRegistry.find_publish_timestamp"
)
@patch("macaron.slsa_analyzer.checks.registry_maintainability_check._check_deprecated")
def test_fail_stale_release(
    mock_deprecated: MagicMock,
    mock_timestamp: MagicMock,
    macaron_path: Path,
    tmp_path: Path,
) -> None:
    """The check fails when the last release exceeds the inactivity threshold."""
    _load_registry_config(tmp_path, threshold_days=365)
    stale = datetime.now(timezone.utc) - timedelta(days=500)
    mock_timestamp.return_value = stale
    mock_deprecated.return_value = (False, None)

    check = RegistryMaintainabilityCheck()
    ctx = _mock_pypi_ctx(macaron_path)
    assert check.run_check(ctx).result_type == CheckResultType.FAILED


@patch(
    "macaron.slsa_analyzer.package_registry.package_registry.PackageRegistry.find_publish_timestamp"
)
@patch("macaron.slsa_analyzer.checks.registry_maintainability_check._check_deprecated")
def test_fail_yanked_pypi(
    mock_deprecated: MagicMock,
    mock_timestamp: MagicMock,
    macaron_path: Path,
    tmp_path: Path,
) -> None:
    """The check fails immediately when a PyPI release is yanked, regardless of age."""
    _load_registry_config(tmp_path)
    recent = datetime.now(timezone.utc) - timedelta(days=10)
    mock_timestamp.return_value = recent
    mock_deprecated.return_value = (True, "Security vulnerability discovered.")

    check = RegistryMaintainabilityCheck()
    ctx = _mock_pypi_ctx(macaron_path)
    assert check.run_check(ctx).result_type == CheckResultType.FAILED


@patch(
    "macaron.slsa_analyzer.package_registry.package_registry.PackageRegistry.find_publish_timestamp"
)
@patch("macaron.slsa_analyzer.checks.registry_maintainability_check._check_deprecated")
def test_fail_deprecated_npm(
    mock_deprecated: MagicMock,
    mock_timestamp: MagicMock,
    macaron_path: Path,
    tmp_path: Path,
) -> None:
    """The check fails immediately when an npm package version is deprecated."""
    _load_registry_config(tmp_path)
    recent = datetime.now(timezone.utc) - timedelta(days=10)
    mock_timestamp.return_value = recent
    mock_deprecated.return_value = (True, "Use express@5 instead.")

    check = RegistryMaintainabilityCheck()
    npm_registry = NPMRegistry()
    npm_registry.load_defaults()
    registry_info = PackageRegistryInfo(ecosystem="npm", package_registry=npm_registry)

    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", purl=_NPM_PURL)
    ctx.dynamic_data["package_registries"] = [registry_info]
    ctx.dynamic_data["git_service"] = NoneGitService()
    assert check.run_check(ctx).result_type == CheckResultType.FAILED


@patch(
    "macaron.slsa_analyzer.package_registry.package_registry.PackageRegistry.find_publish_timestamp"
)
@patch("macaron.slsa_analyzer.checks.registry_maintainability_check._check_deprecated")
@patch("macaron.slsa_analyzer.git_service.github.GitHub.api_client")
def test_fail_archived_repo(
    mock_api_client: MagicMock,
    mock_deprecated: MagicMock,
    mock_timestamp: MagicMock,
    macaron_path: Path,
    tmp_path: Path,
) -> None:
    """The check fails when the GitHub repository is archived, even if release is recent."""
    _load_registry_config(tmp_path)
    recent = datetime.now(timezone.utc) - timedelta(days=10)
    mock_timestamp.return_value = recent
    mock_deprecated.return_value = (False, None)
    mock_api_client.get_repo_data.return_value = {
        "archived": True,
        "pushed_at": (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }

    check = RegistryMaintainabilityCheck()
    ctx = _mock_pypi_ctx(macaron_path)
    ctx.dynamic_data["git_service"] = _make_github_service()
    assert check.run_check(ctx).result_type == CheckResultType.FAILED


@patch(
    "macaron.slsa_analyzer.package_registry.package_registry.PackageRegistry.find_publish_timestamp"
)
@patch("macaron.slsa_analyzer.checks.registry_maintainability_check._check_deprecated")
@patch("macaron.slsa_analyzer.git_service.github.GitHub.api_client")
def test_fail_stale_commit(
    mock_api_client: MagicMock,
    mock_deprecated: MagicMock,
    mock_timestamp: MagicMock,
    macaron_path: Path,
    tmp_path: Path,
) -> None:
    """The check fails when the last commit exceeds the threshold, even if release is recent."""
    _load_registry_config(tmp_path, threshold_days=365)
    recent = datetime.now(timezone.utc) - timedelta(days=30)
    stale_push = datetime.now(timezone.utc) - timedelta(days=500)
    mock_timestamp.return_value = recent
    mock_deprecated.return_value = (False, None)
    mock_api_client.get_repo_data.return_value = {
        "archived": False,
        "pushed_at": stale_push.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    check = RegistryMaintainabilityCheck()
    ctx = _mock_pypi_ctx(macaron_path)
    ctx.dynamic_data["git_service"] = _make_github_service()
    assert check.run_check(ctx).result_type == CheckResultType.FAILED


@patch(
    "macaron.slsa_analyzer.package_registry.package_registry.PackageRegistry.find_publish_timestamp"
)
@patch("macaron.slsa_analyzer.checks.registry_maintainability_check._check_deprecated")
def test_custom_threshold(
    mock_deprecated: MagicMock,
    mock_timestamp: MagicMock,
    macaron_path: Path,
    tmp_path: Path,
) -> None:
    """The check respects a custom threshold loaded from config."""
    _load_registry_config(tmp_path, threshold_days=60)
    # 90 days exceeds the 60-day threshold.
    slightly_stale = datetime.now(timezone.utc) - timedelta(days=90)
    mock_timestamp.return_value = slightly_stale
    mock_deprecated.return_value = (False, None)

    check = RegistryMaintainabilityCheck()
    ctx = _mock_pypi_ctx(macaron_path)
    assert check.run_check(ctx).result_type == CheckResultType.FAILED


@patch(
    "macaron.slsa_analyzer.package_registry.package_registry.PackageRegistry.find_publish_timestamp"
)
@patch("macaron.slsa_analyzer.checks.registry_maintainability_check._check_deprecated")
def test_boundary_at_threshold(
    mock_deprecated: MagicMock,
    mock_timestamp: MagicMock,
    macaron_path: Path,
    tmp_path: Path,
) -> None:
    """The check passes when days_since_release equals the threshold exactly (threshold is exclusive)."""
    _load_registry_config(tmp_path, threshold_days=365)
    # Exactly at threshold: days_since_release == 365, condition is >, so should PASS.
    at_threshold = datetime.now(timezone.utc) - timedelta(days=365)
    mock_timestamp.return_value = at_threshold
    mock_deprecated.return_value = (False, None)

    check = RegistryMaintainabilityCheck()
    ctx = _mock_pypi_ctx(macaron_path)
    assert check.run_check(ctx).result_type == CheckResultType.PASSED


@patch(
    "macaron.slsa_analyzer.package_registry.package_registry.PackageRegistry.find_publish_timestamp"
)
@patch("macaron.slsa_analyzer.checks.registry_maintainability_check._check_deprecated")
@patch("macaron.slsa_analyzer.git_service.github.GitHub.api_client")
def test_skip_github_for_non_github(
    mock_api_client: MagicMock,
    mock_deprecated: MagicMock,
    mock_timestamp: MagicMock,
    macaron_path: Path,
    tmp_path: Path,
) -> None:
    """No GitHub API call is made when the git service is not GitHub; check still runs correctly."""
    _load_registry_config(tmp_path)
    recent = datetime.now(timezone.utc) - timedelta(days=30)
    mock_timestamp.return_value = recent
    mock_deprecated.return_value = (False, None)

    check = RegistryMaintainabilityCheck()
    ctx = _mock_pypi_ctx(macaron_path)
    # git_service is NoneGitService (not GitHub) — API must not be called.
    ctx.dynamic_data["git_service"] = NoneGitService()
    result = check.run_check(ctx)

    mock_api_client.get_repo_data.assert_not_called()
    assert result.result_type == CheckResultType.PASSED
