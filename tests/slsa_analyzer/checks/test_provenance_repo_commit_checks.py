# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This modules contains tests for the provenance available check."""
from pathlib import Path
from typing import TypeVar

import pytest

from macaron.database.table_definitions import CheckFacts, Repository
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType
from macaron.slsa_analyzer.checks.provenance_commit_check import (
    ProvenanceDerivedCommitCheck,
    ProvenanceDerivedCommitFacts,
)
from macaron.slsa_analyzer.checks.provenance_repo_check import ProvenanceDerivedRepoCheck, ProvenanceDerivedRepoFacts
from tests.conftest import MockAnalyzeContext

T = TypeVar("T", bound=CheckFacts)


@pytest.fixture(name="repo_url")
def repo_url_() -> str:
    """Return the repo URL."""
    return "https://github.com/oracle/macaron"


@pytest.fixture(name="commit_digest")
def commit_digest_() -> str:
    """Return the commit digest."""
    return "ba3fcb0c84d6727de343c247a3181908fcd78410"


@pytest.fixture(name="repository")
def repository_(repo_url: str, commit_digest: str) -> Repository:
    """Return the Repository."""
    return Repository(
        complete_name=repo_url.replace("https://", ""),
        remote_path=repo_url,
        commit_sha=commit_digest,
    )


def test_provenance_repo_commit_checks_pass(
    macaron_path: Path,
    repository: Repository,
    repo_url: str,
    commit_digest: str,
) -> None:
    """Test combinations of Repository objects and provenance strings against check."""
    context = _prepare_context(macaron_path, repository)
    context.dynamic_data["provenance_repo"] = repo_url
    context.dynamic_data["provenance_commit"] = commit_digest

    # Check Repo
    repo_result = _perform_check_assert_result_return_result(
        ProvenanceDerivedRepoCheck(), context, CheckResultType.PASSED
    )
    repo_fact = _get_fact(repo_result.result_tables, ProvenanceDerivedRepoFacts)
    assert repo_fact
    assert repo_fact.repository_info == "The repository URL was found from provenance."

    # Check Commit
    commit_result = _perform_check_assert_result_return_result(
        ProvenanceDerivedCommitCheck(), context, CheckResultType.PASSED
    )
    commit_fact = _get_fact(commit_result.result_tables, ProvenanceDerivedCommitFacts)
    assert commit_fact
    assert commit_fact.commit_info == "The commit digest was found from provenance."


def test_provenance_repo_commit_checks_fail(
    macaron_path: Path,
    repository: Repository,
) -> None:
    """Test combinations of Repository objects and provenance strings against check."""
    context = _prepare_context(macaron_path, repository)

    # Check Repo
    _perform_check_assert_result_return_result(ProvenanceDerivedRepoCheck(), context, CheckResultType.FAILED)

    # Check Commit
    _perform_check_assert_result_return_result(ProvenanceDerivedCommitCheck(), context, CheckResultType.FAILED)


def _prepare_context(macaron_path: Path, repository: Repository) -> AnalyzeContext:
    """Prepare a mock AnalyzeContext for performing checks with."""
    context = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    context.component.repository = repository
    return context


def _perform_check_assert_result_return_result(
    check: BaseCheck, context: AnalyzeContext, expected_outcome: CheckResultType
) -> CheckResultData:
    """Run the passed check with the passed context, assert the result matches the expected outcome and return it."""
    result = check.run_check(context)
    assert result.result_type == expected_outcome
    return result


def _get_fact(check_facts: list[CheckFacts], fact_type: type[T]) -> T | None:
    """Return first fact from check result that matches the passed fact type."""
    for fact in check_facts:
        if isinstance(fact, fact_type):
            return fact
    return None
