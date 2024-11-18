# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains tests for the Infer Artifact Pipeline check."""

from pathlib import Path

import pytest

from macaron.database.table_definitions import Repository
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.infer_artifact_pipeline_check import ArtifactPipelineCheck
from tests.conftest import MockAnalyzeContext

RESOURCE_PATH = Path(__file__).parent.joinpath("resources")


@pytest.mark.parametrize(
    ("repository", "expected"),
    [
        (None, CheckResultType.FAILED),
        (
            Repository(complete_name="github.com/package-url/purl-spec", commit_date="2024-01-01T01:01:01+00:00"),
            CheckResultType.FAILED,
        ),
    ],
)
def test_artifact_pipeline_errors(macaron_path: Path, repository: Repository, expected: str) -> None:
    """Test that the check handles repositories correctly."""
    check = ArtifactPipelineCheck()

    # Set up the context object with provenances.
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    ctx.component.repository = repository
    assert check.run_check(ctx).result_type == expected
