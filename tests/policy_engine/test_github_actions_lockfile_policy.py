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
from macaron.database.table_definitions import MappedCheckResult, RepoFinderMetadata
from macaron.policy_engine.policy_engine import run_souffle
from macaron.repo_finder.repo_finder_enums import CommitFinderInfo, RepoFinderInfo
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.github_actions_vulnerability_check import GitHubActionsVulnsCheck
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
