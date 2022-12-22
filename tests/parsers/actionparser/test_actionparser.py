# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the GitHub Actions parser.
"""

import json
import os
from pathlib import Path

from macaron.parsers.actionparser import parse

from ...macaron_testcase import MacaronTestCase


class TestParsers(MacaronTestCase):
    """Test the GitHub Actions parser."""

    def test_actionparser_parse(self) -> None:
        """Test parsing GH Actions workflows."""
        resources_dir = Path(__file__).parent.joinpath("resources")

        valid_results = []
        valid_results.append(
            parse(
                os.path.join(resources_dir, "workflow_files", "codeql-analysis.yml"), str(MacaronTestCase.macaron_path)
            )
        )
        valid_results.append(
            parse(os.path.join(resources_dir, "workflow_files", "maven.yml"), str(MacaronTestCase.macaron_path))
        )
        valid_results.append(
            parse(os.path.join(resources_dir, "workflow_files", "release.yaml"), str(MacaronTestCase.macaron_path))
        )

        expected_results = []
        with open(os.path.join(resources_dir, "expected_results", "codeql-analysis.json"), encoding="utf8") as file:
            expected_results.append(json.load(file))

        with open(os.path.join(resources_dir, "expected_results", "maven.json"), encoding="utf8") as file:
            expected_results.append(json.load(file))

        with open(os.path.join(resources_dir, "expected_results", "release.json"), encoding="utf8") as file:
            expected_results.append(json.load(file))

        for index, valid_item in enumerate(valid_results):
            assert valid_item == expected_results[index]

        # Parse invalid workflows.
        assert (
            parse(os.path.join(resources_dir, "workflow_files", "invalid.yaml"), str(MacaronTestCase.macaron_path))
            == {}
        )
        assert (
            parse(
                os.path.join(resources_dir, "workflow_files", "file_does_not_exist.yaml"),
                str(MacaronTestCase.macaron_path),
            )
            == {}
        )
