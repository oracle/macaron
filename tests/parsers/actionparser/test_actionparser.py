# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the GitHub Actions parser.
"""

import os
from pathlib import Path

import pytest

from macaron import MACARON_PATH
from macaron.errors import ParseError
from macaron.parsers.actionparser import parse

RESOURCES_DIR = Path(__file__).parent.joinpath("resources")


@pytest.mark.parametrize(
    "workflow_path",
    [
        "codeql-analysis.yml",
        "maven.yml",
    ],
)
def test_actionparser_parse(snapshot: dict, workflow_path: str) -> None:
    """Test parsing GH Actions workflows."""
    assert parse(os.path.join(RESOURCES_DIR, "workflow_files", workflow_path), MACARON_PATH) == snapshot


@pytest.mark.parametrize(
    "workflow_path",
    [
        "release.yml",
        "invalid.yml",
        "file_does_not_exist.yml",
    ],
)
def test_actionparser_parse_invalid(workflow_path: str) -> None:
    """Test parsing GH Actions workflows."""
    with pytest.raises(ParseError):
        parse(os.path.join(RESOURCES_DIR, "workflow_files", workflow_path), MACARON_PATH)
