# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the POM parser.
"""

import os
from pathlib import Path

import pytest

from macaron.parsers.pomparser import parse_pom_string as parse

RESOURCES_DIR = Path(__file__).parent.joinpath("resources")


def test_pomparser_parse() -> None:
    """Test parsing GH Actions workflows."""
    with open(os.path.join(RESOURCES_DIR, "valid.xml"), encoding="utf8") as file:
        assert parse(file.read())


@pytest.mark.parametrize(
    "file_name",
    [
        "forbidden_entity.xml",
        "invalid.xml",
    ],
)
def test_pomparser_parse_invalid(file_name: str) -> None:
    """Test parsing GH Actions workflows."""
    with open(os.path.join(RESOURCES_DIR, file_name), encoding="utf8") as file:
        assert not parse(file.read())
