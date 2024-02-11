# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This modules contains tests for the provenance available check."""

import os
from pathlib import Path

from macaron.database.table_definitions import Repository
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.vcs_check import VCSCheck
from tests.conftest import MockAnalyzeContext

from ..mock_git_utils import initiate_repo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.join(BASE_DIR, "mock_repos", "vcs_check_repo/sample_repo")


def test_vcs_check_valid_repo(macaron_path: Path) -> None:
    """Test the vcs check for a valid repo."""
    check = VCSCheck()
    initiate_repo(REPO_DIR)
    use_git_repo = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    use_git_repo.component.repository = Repository(complete_name="github.com/package-url/purl-spec")

    assert check.run_check(use_git_repo).result_type == CheckResultType.PASSED


def test_vcs_check_invalid_repo(macaron_path: Path) -> None:
    """Test the vcs check for an invalid repo."""
    check = VCSCheck()
    initiate_repo(REPO_DIR)
    no_git_repo = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")
    # The repository column is nullable, however, SQLAlchemy does not automatically help mypy to infer that.
    # TODO: remove the type ignore comment below once we add the explicit `None` type to the repository
    # column in the `Component` ORM mapping.
    no_git_repo.component.repository = None  # type: ignore

    assert check.run_check(no_git_repo).result_type == CheckResultType.FAILED
