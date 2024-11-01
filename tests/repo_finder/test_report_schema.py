# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the report schema of the repo finder."""
import json

import pytest

from macaron.repo_finder.report_schema import create_report


@pytest.mark.parametrize(
    ("purl", "commit", "repo"), [("pkg:pypi/macaron@1.0", "commit_digest", "https://github.com/oracle/macaron")]
)
def test_report(purl: str, commit: str, repo: str) -> None:
    """Test creation of reports for standalone repo / commit finder."""
    json_report_str = create_report(purl, commit, repo)
    json_report = json.loads(json_report_str)
    assert json_report
    assert json_report["purl"] == purl
    assert json_report["commit"] == commit
    assert json_report["repo"] == repo
