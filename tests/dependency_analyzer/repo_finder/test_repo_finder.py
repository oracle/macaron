# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the repo finder.
"""

from pathlib import Path

from macaron.config.global_config import global_config
from macaron.dependency_analyzer.repo_finder import parse_gav
from tests.macaron_testcase import MacaronTestCase


class TestDependencyAnalyzer(MacaronTestCase):
    """Test the repo finder functions."""

    CONFIG_DIR = Path(__file__).parent.joinpath("configurations")

    def test_repo_finder(self) -> None:
        """Test the functions of the repo finder that do not require http transactions."""
        global_config.artefact_repositories = ["https://repository.repo/"]
        gav = "group:artifact:version"
        urls = parse_gav(gav)
        assert len(urls) == 1
