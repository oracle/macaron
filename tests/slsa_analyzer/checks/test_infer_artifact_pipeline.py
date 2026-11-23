# Copyright (c) 2023 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains tests for the Infer Artifact Pipeline check."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from macaron.code_analyzer.dataflow_analysis.core import NodeForest
from macaron.database.table_definitions import Repository
from macaron.slsa_analyzer.checks.check_result import CheckResultType, Confidence
from macaron.slsa_analyzer.checks.infer_artifact_pipeline_check import ArtifactPipelineCheck, ArtifactPipelineFacts
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions
from macaron.slsa_analyzer.package_registry.maven_central_registry import MavenCentralRegistry
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from macaron.slsa_analyzer.specs.inferred_provenance import InferredProvenance
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo
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


@pytest.mark.parametrize(
    ("runs_available", "conclusion", "expected"),
    [
        (True, "success", CheckResultType.PASSED),
        (False, "success", CheckResultType.FAILED),
        (True, "failure", CheckResultType.FAILED),
    ],
    ids=["successful-run", "missing-run", "failed-deploy"],
)
def test_artifact_pipeline_workflow_history(
    macaron_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runs_available: bool,
    conclusion: str,
    expected: CheckResultType,
) -> None:
    """Infer a publishing pipeline only when fixed API responses contain a successful deploy."""
    # Synthetic API fixtures preserve success coverage after live workflow history disappears.
    # Freeze the retention clock so the missing-run case cannot age into UNKNOWN.
    clock = Mock(wraps=datetime)
    clock.now.return_value = datetime(2026, 11, 23, tzinfo=UTC)
    monkeypatch.setattr("macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci.datetime", clock)
    monkeypatch.setattr(
        MavenCentralRegistry,
        "find_publish_timestamp",
        lambda self, purl: datetime(2025, 12, 15, 13, tzinfo=UTC),
    )
    run_url = "https://github.com/apache/logging-log4j2/actions/runs/123"
    responses = {
        "https://api.github.com/repos/apache/logging-log4j2/actions/runs?"
        "created=2025-12-15T11%3A00%3A00%2B00%3A00..2025-12-15T13%3A00%3A00%2B00%3A00": {
            "total_count": int(runs_available),
            "workflow_runs": [{"id": 123, "path": ".github/workflows/build.yaml", "html_url": run_url}]
            if runs_available
            else [],
        },
        "https://api.github.com/repos/apache/logging-log4j2/actions/runs/123/jobs": {
            "total_count": 1,
            "jobs": [
                {
                    "name": "deploy / release",
                    "conclusion": conclusion,
                    "started_at": "2025-12-15T12:45:00Z",
                    "steps": [],
                }
            ],
        },
    }
    monkeypatch.setattr(
        "macaron.slsa_analyzer.git_service.api_client.send_get_http", lambda url, headers: responses[url]
    )
    workflow = (
        "https://github.com/apache/logging-log4j2/blob/"
        "028e9fad03ae7bcbf2e49ab8d32d8cfb900f3587/.github/workflows/build.yaml"
    )
    provenance = InferredProvenance()
    predicate = provenance.payload["predicate"]
    assert predicate is not None
    predicate["buildType"] = "Custom github_actions"
    predicate["invocation"] = {"configSource": {"entryPoint": workflow}}
    predicate["buildConfig"] = {"jobID": "deploy", "calleeType": "reusable"}
    ctx = MockAnalyzeContext(
        macaron_path=macaron_path, output_dir="", purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.25.3"
    )
    ctx.component.repository = Repository(
        complete_name="github.com/apache/logging-log4j2",
        full_name="apache/logging-log4j2",
        commit_date="2025-12-15T12:41:25+00:00",
    )
    ctx.dynamic_data["package_registries"] = [PackageRegistryInfo("maven", MavenCentralRegistry())]
    ctx.dynamic_data["ci_services"] = [
        CIInfo(
            service=GitHubActions(),
            callgraph=NodeForest([]),
            provenance_assets=[],
            release={},
            provenances=[],
            build_info_results=InTotoV01Payload(statement=provenance.payload),
        )
    ]

    result = ArtifactPipelineCheck().run_check(ctx)

    assert result.result_type == expected
    if expected == CheckResultType.FAILED:
        assert not result.result_tables
        return
    assert len(result.result_tables) == 1
    facts = result.result_tables[0]
    assert isinstance(facts, ArtifactPipelineFacts)
    assert facts.run_url == run_url
    assert facts.deploy_workflow == workflow
    assert facts.deploy_job == "deploy"
    assert facts.confidence == Confidence.MEDIUM
    assert not facts.from_provenance
    assert not facts.run_deleted
