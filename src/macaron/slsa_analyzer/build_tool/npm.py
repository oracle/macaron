# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the NPM class which inherits BaseBuildTool.

This module is used to work with repositories that use npm/pnpm as its
build tool.
"""

from macaron.config.defaults import defaults
from macaron.dependency_analyzer.dependency_resolver import DependencyAnalyzer, NoneDependencyAnalyzer
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists


class NPM(BaseBuildTool):
    """This class contains the information of the npm/pnpm build tool."""

    def __init__(self) -> None:
        super().__init__(name="npm")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        if "builder.npm" in defaults:
            for item in defaults["builder.npm"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("builder.npm", item))

        if "builder.npm.ci.deploy" in defaults:
            for item in defaults["builder.npm.ci.deploy"]:
                if item in self.ci_deploy_kws:
                    self.ci_deploy_kws[item] = defaults.get_list("builder.npm.ci.deploy", item)

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
        # TODO: When more complex build detection is being implemented, consider
        #       cases like .npmrc existing but not package-lock.json and whether
        #       they would still count as "detected"
        npm_config_files = self.build_configs + self.package_lock + self.entry_conf
        for file in npm_config_files:
            if file_exists(repo_path, file):
                return True

        return False

    def prepare_config_files(self, wrapper_path: str, build_dir: str) -> bool:
        """Prepare the necessary wrapper files for running the build.

        npm/pnpm doesn't require preparation, so return true.

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
