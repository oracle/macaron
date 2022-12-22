# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the bash parser.
"""

import json
import os
from pathlib import Path

from macaron.parsers.bashparser import parse

from ...macaron_testcase import MacaronTestCase


class TestParsers(MacaronTestCase):
    """Test the bash parser."""

    def test_bashparser_parse(self) -> None:
        """Test parsing bash scripts."""
        resources_dir = Path(__file__).parent.joinpath("resources")

        # Parse the valid mock bash script.
        # We get the MACARON_PATH directly from the __main__ file
        # because it's not set in the global config object during unit testing.
        valid_tests = [
            {"bash_file": "valid.sh", "expected_json": "valid.json"},
            {"bash_file": "valid_github_action_bash.sh", "expected_json": "valid_github_action_bash.json"},
        ]
        for valid_test in valid_tests:
            with open(
                os.path.join(resources_dir, "bash_files", valid_test["bash_file"]), encoding="utf8"
            ) as bash_file, open(
                os.path.join(resources_dir, "expected_results", valid_test["expected_json"]), encoding="utf8"
            ) as expected_file:
                valid_result = parse(bash_file.read(), str(self.macaron_path))
                expected_result = json.load(expected_file)
                assert valid_result == expected_result

        # Parse invalid workflows.
        with open(os.path.join(resources_dir, "bash_files", "invalid.sh"), encoding="utf8") as bash_file:
            assert not parse(bash_file.read(), str(MacaronTestCase.macaron_path))
