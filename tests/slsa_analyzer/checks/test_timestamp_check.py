# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains tests for the Timestamp Check."""
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer

from macaron.database.table_definitions import Repository
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.timestamp_check import TimestampCheck
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo
from macaron.database.db_custom_types import RFC3339DateTime
from tests.conftest import MockAnalyzeContext

@pytest.mark.parametrize(
    ("repository", "package_registry_info_entries", "expected"),
    [
        (None, [], CheckResultType.FAILED),
        (Repository(complete_name="github.com/package-url/purl-spec", commit_date=RFC3339DateTime()), [], CheckResultType.FAILED),
        (Repository(complete_name="github.com/package-url/purl-spec", commit_date=RFC3339DateTime()), [{"build_tool": "Maven", "package_registry": "MavenCentralRegistry"}], CheckResultType.FAILED),
        (Repository(complete_name="github.com/package-url/purl-spec", commit_date=RFC3339DateTime() - timedelta(days=2)), [{"build_tool": "Maven", "package_registry": "MavenCentralRegistry", "published_date": RFC3339DateTime() - timedelta(hours=25)}], CheckResultType.PASSED),
    ],
)
def test_timestamp_check(httpserver: HTTPServer, macaron_path: Path, repository: Repository, package_registry_info_entries: list, expected: str) -> None:
    """Test that the check handles repositories and package registry info correctly."""
    check = TimestampCheck()

    # Set up the context object with dynamic data and repository.
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.component.repository = repository
    ctx.dynamic_data["package_registries"] = package_registry_info_entries

    # Mock the find_publish_timestamp method for MavenCentralRegistry using the httpserver
    httpserver.expect_request("/maven-central-timestamp").respond_with_json({"published_date": "2024-08-29T12:00:00Z"})

    # Replace the MavenCentralRegistry with the mock
    for entry in package_registry_info_entries:
        if entry["package_registry"] == "MavenCentralRegistry":
            entry["package_registry"] = httpserver.url_for("/maven-central-timestamp")

    assert check.run_check(ctx).result_type == expected