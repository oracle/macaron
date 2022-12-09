# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Build Script Check for Gradle build tool."""


import os
from pathlib import Path

from macaron.slsa_analyzer.build_tool import Gradle
from macaron.slsa_analyzer.build_tool.base_build_tool import _find_parent_file_in

from ...macaron_testcase import MacaronTestCase
from ..mock_git_utils import prepare_repo_for_testing


class TestGradleBuildTool(MacaronTestCase):
    """Test the gradle build tool."""

    def test_gradle_build_tool(self) -> None:
        """Test the gradle build tool."""
        base_dir = Path(__file__).parent
        repo_dir = base_dir.joinpath("mock_repos", "gradle_repos")

        # The path of mock repositories
        no_setting_gradle = repo_dir.joinpath("no_gradle")
        groovy_setting_gradle = repo_dir.joinpath("groovy_gradle")
        kotlin_setting_gradle = repo_dir.joinpath("kotlin_gradle")

        if not os.path.isdir(repo_dir):
            os.makedirs(repo_dir)

        gradle_tool = Gradle()
        gradle_tool.load_defaults()
        no_gradle = prepare_repo_for_testing(no_setting_gradle, self.macaron_path, base_dir)
        groovy_gradle = prepare_repo_for_testing(groovy_setting_gradle, self.macaron_path, base_dir)
        kotlin_gradle = prepare_repo_for_testing(kotlin_setting_gradle, self.macaron_path, base_dir)

        # A repo without gradle
        assert not gradle_tool.is_detected(no_gradle.git_obj.path)
        assert not _find_parent_file_in(no_gradle.git_obj.path, "settings.gradle")
        assert not _find_parent_file_in(no_gradle.git_obj.path, "settings.gradle.kts")

        # A repo with groovy gradle
        assert gradle_tool.is_detected(groovy_gradle.git_obj.path)
        assert _find_parent_file_in(groovy_gradle.git_obj.path, "settings.gradle")
        assert not _find_parent_file_in(groovy_gradle.git_obj.path, "settings.gradle.kts")

        # A repo with kotlin gradle
        assert gradle_tool.is_detected(kotlin_gradle.git_obj.path)
        assert not _find_parent_file_in(kotlin_gradle.git_obj.path, "settings.gradle")
        assert _find_parent_file_in(kotlin_gradle.git_obj.path, "settings.gradle.kts")
