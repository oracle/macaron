# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the repo finder.
"""
import os
from pathlib import Path

from macaron.config.global_config import global_config
from macaron.dependency_analyzer.repo_finder import parse_gav, parse_pom
from tests.macaron_testcase import MacaronTestCase


class TestDependencyAnalyzer(MacaronTestCase):
    """Test the repo finder functions."""

    def test_repo_finder(self) -> None:
        """Test the functions of the repo finder that do not require http transactions."""
        global_config.artefact_repositories = ["https://repository.repo/"]
        gav = "group:artifact:version"
        created_urls = parse_gav(gav)
        assert len(created_urls) == 1

        resources_dir = Path(__file__).parent.joinpath("resources")
        with open(os.path.join(resources_dir, "example_pom.xml"), encoding="utf8") as file:
            found_urls = parse_pom(file.read(), ["scm.url"])
            assert len(found_urls) == 1
            assert found_urls[0] == "https://example.example/example"
