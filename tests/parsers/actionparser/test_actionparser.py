# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the GitHub Actions parser.
"""

import os
from pathlib import Path

import pytest

from macaron import MACARON_PATH
from macaron.parsers.actionparser import parse

RESOURCES_DIR = Path(__file__).parent.joinpath("resources")


@pytest.mark.parametrize(
    "workflow_path",
    [
        "codeql-analysis.yml",
        "maven.yml",
        "release.yml",
        "invalid.yml",
        "file_does_not_exist.yml",
    ],
)
def test_actionparser_parse(snapshot: dict, workflow_path: str) -> None:
    """Test parsing GH Actions workflows."""
    assert parse(os.path.join(RESOURCES_DIR, "workflow_files", workflow_path), str(MACARON_PATH)) == snapshot
