# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the report schema of the repo finder."""
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from macaron.repo_finder.repo_utils import create_report


@pytest.fixture(name="json_schema")
def json_schema_() -> Any:
    """Load and return the JSON schema."""
    with open(Path(__file__).parent.joinpath("resources", "find_source_report_schema.json"), encoding="utf-8") as file:
        return json.load(file)


@pytest.mark.parametrize(
    ("purl", "commit", "repo"), [("pkg:pypi/macaron@1.0", "commit_digest", "https://github.com/oracle/macaron")]
)
def test_report(purl: str, commit: str, repo: str, json_schema: Any) -> None:
    """Test creation of reports for standalone repo / commit finder."""
    json_report_str = create_report(purl, commit, repo)
    json_report = json.loads(json_report_str)

    jsonschema.validate(
        schema=json_schema,
        instance=json_report,
    )
