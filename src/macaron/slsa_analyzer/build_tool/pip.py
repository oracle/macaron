# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Pip class which inherits BaseBuildTool.

This module is used to work with repositories that use pip for dependency management.
"""

import logging
import os
import tomllib

from macaron.config.defaults import defaults
from macaron.dependency_analyzer import DependencyAnalyzer, NoneDependencyAnalyzer
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists

logger: logging.Logger = logging.getLogger(__name__)


class Pip(BaseBuildTool):
    """This class contains the information of the pip build tool."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="pip")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        if "builder.pip" in defaults:
            for item in defaults["builder.pip"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("builder.pip", item))

        if "builder.pip.ci.deploy" in defaults:
            for item in defaults["builder.pip.ci.deploy"]:
                if item in self.ci_deploy_kws:
                    self.ci_deploy_kws[item] = defaults.get_list("builder.pip.ci.deploy", item)

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
        for file in self.build_configs:
            if file_exists(repo_path, file):
                # Find project name value from the config file.
                # TODO: improve this approach, support setup.py
                file_path = os.path.join(repo_path, file)
                if file == "pyproject.toml":
                    try:
                        with open(file_path, "rb") as toml_file:
                            try:
                                data = tomllib.load(toml_file)
                                project = data.get("project", {})
                                if project:
                                    # Store the project name
                                    self.project_name = project.get("name", "")
                                    logger.info("Package name: %s", self.project_name)
                            except tomllib.TOMLDecodeError:
                                logger.debug("Failed to read the %s file: invalid toml file.", file)
                    except FileNotFoundError:
                        logger.debug("Failed to read the %s file.", file)
                return True
        return False

    def prepare_config_files(self, wrapper_path: str, build_dir: str) -> bool:
        """Prepare the necessary wrapper files for running the build.

        This method returns False on errors. Pip doesn't require any preparation, therefore this method always
        returns True.

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
