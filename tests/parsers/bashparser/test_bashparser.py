# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the bash parser.
"""

import json
import os
from pathlib import Path

import pytest

from macaron import MACARON_PATH
from macaron.errors import ParseError
from macaron.parsers.bashparser import parse, parse_file


@pytest.mark.parametrize(
    ("script_file_name", "expected_json_file_name"),
    [
        ("valid.sh", "valid.json"),
        ("valid_github_action_bash.sh", "valid_github_action_bash.json"),
    ],
)
def test_bashparser_parse(script_file_name: str, expected_json_file_name: str) -> None:
    """Test parsing bash scripts."""
    resources_dir = Path(__file__).parent.joinpath("resources")

    # Parse the bash scripts.
    with (
        open(os.path.join(resources_dir, "bash_files", script_file_name), encoding="utf8") as bash_file,
        open(
            os.path.join(resources_dir, "expected_results", expected_json_file_name), encoding="utf8"
        ) as expected_file,
    ):
        result = parse(bash_file.read(), MACARON_PATH)
        expected_result = json.load(expected_file)
        assert result == expected_result


def test_bashparser_parse_invalid() -> None:
    """Test parsing invalid bash script."""
    resources_dir = Path(__file__).parent.joinpath("resources")
    file_path = os.path.join(resources_dir, "invalid.sh")
    # Parse the bash script file.
    with pytest.raises(ParseError):
        parse_file(file_path=file_path, macaron_path=MACARON_PATH)
