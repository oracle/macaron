# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Go class which inherits BaseBuildTool.

This module is used to work with repositories that have Go.
"""

from macaron.config.defaults import defaults
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer, NoneDependencyAnalyzer
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists
from macaron.slsa_analyzer.build_tool.language import BuildLanguage


class Go(BaseBuildTool):
    """This class contains the information of the Go build tool."""

    def __init__(self) -> None:
        super().__init__(name="go", language=BuildLanguage.GO, purl_type="golang")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        if "builder.go" in defaults:
            for item in defaults["builder.go"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("builder.go", item))

        if "builder.go.ci.deploy" in defaults:
            for item in defaults["builder.go.ci.deploy"]:
                if item in self.ci_deploy_kws:
                    self.ci_deploy_kws[item] = defaults.get_list("builder.go.ci.deploy", item)

    def is_detected(self, repo_path: str) -> bool:
        """Return True if this build tool is used in the target repo.

        Parameters
        ----------
        repo_path : str
            The path to the target repo.

        Returns
        -------
        bool
            True if this build tool is detected, else False.
        """
        go_config_files = self.build_configs + self.entry_conf
        for file in go_config_files:
            if file_exists(repo_path, file):
                return True

        return False

    def prepare_config_files(self, wrapper_path: str, build_dir: str) -> bool:
        """Prepare the necessary wrapper files for running the build.

        Go doesn't require preparation, so return true.

        Parameters
        ----------
        wrapper_path : str
            The path where all necessary wrapper files are located.
        build_dir : str
            The path of the build dir. This is where all files are copied to.

        Returns
        -------
        bool
            True if succeed else False.
        """
        return True

    def get_dep_analyzer(self, repo_path: str) -> DependencyAnalyzer:
        """Create a DependencyAnalyzer for the build tool.

        Parameters
        ----------
        repo_path: str
            The path to the target repo.

        Returns
        -------
        DependencyAnalyzer
            The DependencyAnalyzer object.
        """
        # TODO: Implement this method.
        return NoneDependencyAnalyzer()
