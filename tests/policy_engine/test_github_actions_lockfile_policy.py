# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Exercise actual check facts, SQLite views, the shipped policy, and action diagnostics."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from macaron.database.database_manager import DatabaseManager
from macaron.database.table_definitions import CheckFacts, MappedCheckResult, RepoFinderMetadata
from macaron.policy_engine.policy_engine import run_souffle
from macaron.repo_finder.repo_finder_enums import CommitFinderInfo, RepoFinderInfo
from macaron.slsa_analyzer.checks.check_result import CheckResultType, Confidence
from macaron.slsa_analyzer.checks.github_actions_vulnerability_check import (
    GitHubActionsVulnsCheck,
    GitHubActionsVulnsFacts,
)
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService
from macaron.slsa_analyzer.package_registry.osv_dev import OSVDevService
from tests.conftest import MockAnalyzeContext
from tests.output_reporter.test_write_job_summary import _load_write_job_summary_module
from tests.parsers.test_github_actions_lockfile import write_lockfile
from tests.slsa_analyzer.checks.test_github_actions_vulnerability_check import get_ci_info


@pytest.mark.parametrize(
    ("mode", "passed"),
    [("locked", True), ("uncovered", False), ("invalid", False), ("vulnerable", False), ("permissions", False)],
)
def test_lockfile_policy_database_and_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ci_services: dict[str, BaseCIService],
    mode: str,
    passed: bool,
) -> None:
    """The shipped policy consumes real results instead of masking incorrect pinning or OSV versions."""
    directory = tmp_path / ".github/workflows"
    directory.mkdir(parents=True)
    source = directory / "ci.yml"
    permissions = "write-all" if mode == "permissions" else "{}"
    source.write_text(
        f"""on: push
permissions: {permissions}
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: example/parent@v1
""",
        encoding="utf-8",
    )
    path = write_lockfile(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if mode == "invalid":
        data["version"] = "v99.0.0"
    if mode != "uncovered":
        (directory / "actions.lock").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(
        OSVDevService,
        "get_vulnerabilities_package_name_batch",
        lambda packages: packages if mode == "vulnerable" else [],
    )
    monkeypatch.setattr(OSVDevService, "get_vulnerabilities_package_name", lambda **_: [{"id": "TEST-1"}])
    monkeypatch.setattr(OSVDevService, "is_version_affected", lambda *args, **_: args[2] == "b" * 40)
    monkeypatch.setattr(ci_services["github_actions"].api_client, "get_commit_sha_from_ref", lambda *_: None)
    ctx = MockAnalyzeContext(fs_path=str(tmp_path), purl="pkg:github.com/example/target@" + "d" * 40)
    ctx.dynamic_data["ci_services"] = [get_ci_info(ci_services, "github_actions", str(source))]
    ctx.component.type, ctx.component.name = "github.com", "target"
    ctx.component.analysis.analysis_time = datetime.now(UTC)
    ctx.component.analysis.macaron_version = "test"
    ctx.component.repo_finder_metadata = RepoFinderMetadata(
        repo_finder_outcome=RepoFinderInfo.NOT_USED,
        commit_finder_outcome=CommitFinderInfo.NOT_USED,
        found_url="",
        found_commit="",
    )
    repository = ctx.component.repository
    repository.full_name, repository.type, repository.name = "example/target", "github.com", "target"
    repository.remote_path, repository.commit_date = "https://github.com/example/target", "2026-11-13"
    result = GitHubActionsVulnsCheck().run_check(ctx)
    assert (result.result_type == CheckResultType.PASSED) is passed
    manager = DatabaseManager(str(tmp_path / "macaron.db"))
    manager.create_tables()
    check = MappedCheckResult(check_id="mcn_githubactions_vulnerabilities_1", passed=passed, component=ctx.component)
    for fact in result.result_tables:
        fact.checkresult, fact.component = check, ctx.component
    try:
        with Session(manager.engine) as session:
            session.add(ctx.component)
            session.commit()
        root = Path(__file__).resolve().parents[2]
        resources = root / "src/macaron/resources/policies"
        template = (resources / "datalog/check-github-actions.dl.template").read_text(encoding="utf-8")
        policy = template.replace("<PACKAGE_PURL>", "pkg:github.com/example/target@.*")
        output = run_souffle(str(tmp_path / "macaron.db"), policy)
        assert output["passed_policies"] == ([["github_actions_vulns"]] if passed else [])
        assert output["failed_policies"] == ([] if passed else [["github_actions_vulns"]])
        module = _load_write_job_summary_module()
        with closing(sqlite3.connect(tmp_path / "macaron.db")) as connection:
            module.validate_github_actions_schema(connection)
            cursor = connection.execute((resources / "sql/check-github-actions.sql").read_text(encoding="utf-8"))
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
        assert bool(rows) is not passed
        if rows:
            summary = tmp_path / "summary.md"
            assert module.write_compact_gha_vuln_diagnostics(summary, columns, rows) is True
            text = summary.read_text(encoding="utf-8")
            if mode == "vulnerable":
                assert "b" * 40 in text
                assert "example/parent@v1" in text
    finally:
        manager.engine.dispose()


@pytest.mark.parametrize("case", ["log4j_purl", "log4j_repo", "coherence"])
@pytest.mark.parametrize("include_finding", [True, False])
def test_integration_github_actions_policies(tmp_path: Path, case: str, include_finding: bool) -> None:
    """Integration policies require the intended finding and compile against the current schema."""
    coherence = case == "coherence"
    purl = (
        "pkg:github.com/oracle/coherence-js-client@39166341bc31f75b663ff439dae36170fb3e99a9"
        if coherence
        else "pkg:maven/org.apache.logging.log4j/log4j-core@2.25.3"
    )
    ctx = MockAnalyzeContext(purl=purl)
    ctx.component.analysis.analysis_time = datetime.now(UTC)
    ctx.component.analysis.macaron_version = "test"
    ctx.component.type, ctx.component.name = (
        ("github.com", "coherence-js-client") if coherence else ("maven", "log4j-core")
    )
    ctx.component.repo_finder_metadata = RepoFinderMetadata(
        repo_finder_outcome=RepoFinderInfo.NOT_USED,
        commit_finder_outcome=CommitFinderInfo.NOT_USED,
        found_url="",
        found_commit="",
    )
    repository = ctx.component.repository
    repository.full_name = "oracle/coherence-js-client" if coherence else "apache/logging-log4j2"
    repository.remote_path = f"https://github.com/{repository.full_name}"
    repository.type, repository.name = "github.com", repository.full_name.split("/")[-1]
    repository.commit_date = "2026-11-13"
    check = MappedCheckResult(check_id="mcn_githubactions_vulnerabilities_1", passed=False, component=ctx.component)
    for check_id, passed in {
        "mcn_build_as_code_1": True,
        "mcn_build_script_1": True,
        "mcn_build_service_1": True,
        "mcn_find_artifact_pipeline_1": True,
        "mcn_version_control_system_1": True,
        "mcn_provenance_available_1": False,
        "mcn_provenance_derived_commit_1": False,
        "mcn_provenance_derived_repo_1": False,
        "mcn_provenance_expectation_1": False,
        "mcn_provenance_witness_level_one_1": False,
        "mcn_trusted_builder_level_three_1": False,
    }.items():
        result = MappedCheckResult(check_id=check_id, passed=passed, component=ctx.component)
        if check_id == "mcn_find_artifact_pipeline_1":
            CheckFacts(checkresult=result, component=ctx.component, confidence=0.7)
    if include_finding:
        GitHubActionsVulnsFacts(
            # Finding identifiers must not accidentally equal the component identifier.
            id=101,
            checkresult=check,
            component=ctx.component,
            confidence=Confidence.HIGH,
            caller_workflow=(
                "https://github.com/oracle/coherence-js-client/blob/39166341bc31f75b663ff439dae36170fb3e99a9/.github/workflows/trivy-scan.yml"
                if coherence
                else "https://github.com/apache/logging-log4j2/blob/028e9fad03ae7bcbf2e49ab8d32d8cfb900f3587/.github/workflows/build.yaml"
            ),
            finding_type="known-vulnerability" if coherence else "unpinned-third-party-action",
            finding_group="third_party_action_risk",
            finding_priority=20,
            action_name="aquasecurity/trivy-action"
            if coherence
            else "apache/logging-parent/.github/workflows/build-reusable.yaml",
            action_ref="0.32.0" if coherence else "rel/12.1.1",
            sha_pinned=False,
            vuln_urls=[
                "https://osv.dev/vulnerability/GHSA-69fq-xp46-6x23",
                "https://osv.dev/vulnerability/GHSA-9p44-j4g5-cfx5",
            ]
            if coherence
            else [],
        )
    manager = DatabaseManager(str(tmp_path / "macaron.db"))
    manager.create_tables()
    try:
        with Session(manager.engine) as session:
            session.add(ctx.component)
            session.commit()
        directory = "oracle_coherence-js-client" if coherence else "org_apache_logging_log4j"
        filename = "policy.dl" if coherence else "policy_purl.dl" if case == "log4j_purl" else "policy_repo_url.dl"
        policy_path = Path(__file__).resolve().parents[1] / "integration/cases" / directory / filename
        output = run_souffle(str(tmp_path / "macaron.db"), policy_path.read_text(encoding="utf-8"))
        assert bool(output["passed_policies"]) is include_finding
        assert bool(output["failed_policies"]) is not include_finding
    finally:
        manager.engine.dispose()
