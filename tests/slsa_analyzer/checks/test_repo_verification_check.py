# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Module to test the repository verification check."""

from pathlib import Path

from macaron.repo_verifier.repo_verifier_base import RepositoryVerificationResult, RepositoryVerificationStatus
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.scm_authenticity_check import ScmAuthenticityCheck
from macaron.slsa_analyzer.package_registry import PyPIRegistry
from macaron.slsa_analyzer.package_registry.maven_central_registry import MavenCentralRegistry
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo
from tests.conftest import MockAnalyzeContext

RESOURCE_PATH = Path(__file__).parent.joinpath("resources")


def test_repo_verification_pass(maven_tool: BaseBuildTool, macaron_path: Path) -> None:
    """Test that the check passes when the repository is verified."""
    check = ScmAuthenticityCheck()

    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", purl="pkg:maven/test/test")
    maven_registry = MavenCentralRegistry()
    ctx.dynamic_data["package_registries"] = [PackageRegistryInfo(maven_tool.purl_type, maven_registry)]
    ctx.dynamic_data["repo_verification"] = [
        RepositoryVerificationResult(
            status=RepositoryVerificationStatus.PASSED,
            reason="",
            build_tool=maven_tool,
        )
    ]

    assert check.run_check(ctx).result_type == CheckResultType.PASSED


def test_repo_verification_fail(maven_tool: BaseBuildTool, macaron_path: Path) -> None:
    """Test that the check fails when the repository verification is failed."""
    check = ScmAuthenticityCheck()

    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", purl="pkg:maven/test/test")
    maven_registry = MavenCentralRegistry()
    ctx.dynamic_data["package_registries"] = [PackageRegistryInfo(maven_tool.purl_type, maven_registry)]
    ctx.dynamic_data["repo_verification"] = [
        RepositoryVerificationResult(
            status=RepositoryVerificationStatus.FAILED,
            reason="",
            build_tool=maven_tool,
        )
    ]

    assert check.run_check(ctx).result_type == CheckResultType.FAILED


def test_check_unknown_for_unknown_repo_verification(maven_tool: BaseBuildTool, macaron_path: Path) -> None:
    """Test that the check returns unknown when the repository verification is unknown."""
    check = ScmAuthenticityCheck()

    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", purl="pkg:maven/test/test")
    maven_registry = MavenCentralRegistry()
    ctx.dynamic_data["package_registries"] = [PackageRegistryInfo(maven_tool.purl_type, maven_registry)]
    ctx.dynamic_data["repo_verification"] = [
        RepositoryVerificationResult(
            status=RepositoryVerificationStatus.UNKNOWN,
            reason="",
            build_tool=maven_tool,
        )
    ]

    assert check.run_check(ctx).result_type == CheckResultType.UNKNOWN


def test_check_unknown_for_unsupported_build_tools(pip_tool: BaseBuildTool, macaron_path: Path) -> None:
    """Test that the check returns unknown for unsupported build tools."""
    check = ScmAuthenticityCheck()

    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="", purl="pkg:pypi/test/test")
    pypi_registry = PyPIRegistry()
    ctx.dynamic_data["package_registries"] = [PackageRegistryInfo(pip_tool.purl_type, pypi_registry)]

    assert check.run_check(ctx).result_type == CheckResultType.UNKNOWN
