# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the bash parser.
"""

import json
import os
from pathlib import Path

import pytest

from macaron import MACARON_PATH
from macaron.code_analyzer.call_graph import BaseNode
from macaron.errors import CallGraphError
from macaron.parsers.bashparser import BashScriptType, create_bash_node, parse


@pytest.mark.parametrize(
    ("script_file_name", "expected_json_file_name"),
    [
        ("valid.sh", "valid.json"),
        ("valid_github_action_bash.sh", "valid_github_action_bash.json"),
        ("invalid.sh", "invalid.json"),
    ],
)
def test_bashparser_parse(script_file_name: str, expected_json_file_name: str) -> None:
    """Test parsing bash scripts."""
    resources_dir = Path(__file__).parent.joinpath("resources")

    # Parse the bash scripts.
    with open(os.path.join(resources_dir, "bash_files", script_file_name), encoding="utf8") as bash_file, open(
        os.path.join(resources_dir, "expected_results", expected_json_file_name), encoding="utf8"
    ) as expected_file:
        result = parse(bash_file.read(), MACARON_PATH)
        expected_result = json.load(expected_file)
        assert result == expected_result


def test_create_bash_node_recursively() -> None:
    """Test creating bash nodes from recursive script."""
    resources_dir = Path(__file__).parent.joinpath("resources", "bash_files")
    with pytest.raises(CallGraphError, match="The analysis has reached maximum recursion depth .*"):
        create_bash_node(
            name="run",
            node_id=None,
            node_type=BashScriptType.FILE,
            source_path=os.path.join(resources_dir, "recursive.sh"),
            ci_step_ast=None,
            repo_path=str(resources_dir),
            caller=BaseNode(),
            recursion_depth=0,
            macaron_path=MACARON_PATH,
        )


def test_create_bash_node_path_traversal_attack() -> None:
    """Test creating bash nodes from a script that is vulnerable to path traversal attacks."""
    resources_dir = Path(__file__).parent.joinpath("resources", "bash_files")
    assert not create_bash_node(
        name="run",
        node_id=None,
        node_type=BashScriptType.FILE,
        source_path=os.path.join(resources_dir, "path_traversal.sh"),
        ci_step_ast=None,
        repo_path=str(resources_dir),
        caller=BaseNode(),
        recursion_depth=0,
        macaron_path=MACARON_PATH,
    ).callee
