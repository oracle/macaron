# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Maven build tool."""

import os
from pathlib import Path

from macaron.slsa_analyzer.build_tool import Maven
from macaron.slsa_analyzer.build_tool.base_build_tool import _find_parent_file_in

from ...macaron_testcase import MacaronTestCase
from ..mock_git_utils import prepare_repo_for_testing


class TestMavenBuildTool(MacaronTestCase):
    """Test the Maven build tool."""

    def test_maven_build_tool(self) -> None:
        """Test the Maven build tool."""
        base_dir = Path(__file__).parent
        repo_dir = base_dir.joinpath("mock_repos", "maven_repos")

        # The path of mock repositories
        has_parent_pom = repo_dir.joinpath("has_parent_pom")
        no_parent_pom = repo_dir.joinpath("no_parent_pom")
        no_pom = repo_dir.joinpath("no_pom")

        if not os.path.isdir(repo_dir):
            os.makedirs(repo_dir)

        maven_tool = Maven()
        maven_tool.load_defaults()

        # A repo with no pom
        no_pom_repo = prepare_repo_for_testing(no_pom, self.macaron_path, base_dir)
        assert not maven_tool.is_detected(no_pom_repo.git_obj.path)
        assert not _find_parent_file_in(no_pom_repo.git_obj.path, "pom.xml")

        # A repo with pom for each sub-module but no parent pom
        no_parent_pom_repo = prepare_repo_for_testing(no_parent_pom, self.macaron_path, base_dir)
        assert maven_tool.is_detected(no_parent_pom_repo.git_obj.path)
        assert not _find_parent_file_in(no_parent_pom_repo.git_obj.path, "pom.xml")

        # A repo with pom for each sub-module and parent pom
        has_parent_pom_repo = prepare_repo_for_testing(has_parent_pom, self.macaron_path, base_dir)
        assert maven_tool.is_detected(has_parent_pom_repo.git_obj.path)
        assert _find_parent_file_in(has_parent_pom_repo.git_obj.path, "pom.xml")
