# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Poetry class which inherits BaseBuildTool.

This module is used to work with repositories that use Poetry for dependency management.
"""

import logging
import tomllib

from macaron.config.defaults import defaults
from macaron.dependency_analyzer import DependencyAnalyzer, NoneDependencyAnalyzer
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists, find_files

logger: logging.Logger = logging.getLogger(__name__)


class Poetry(BaseBuildTool):
    """This class contains the information of the poetry build tool."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="poetry")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        if "builder.poetry" in defaults:
            for item in defaults["builder.poetry"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("builder.poetry", item))

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
                return True

        for conf in self.entry_conf:
            # Find the paths of all pyproject.toml files.
            files_detected = find_files(repo_path, conf)

            if files_detected:
                try:
                    # Take the highest level file (shortest file path)
                    file_path = min(files_detected, key=len)

                    # Parse the .toml file
                    with open(file_path, "rb") as toml_file:
                        data = tomllib.load(toml_file)
                        if ("tool" in data) and ("poetry" in data["tool"]):
                            return True
                    return False
                except FileNotFoundError:
                    logger.error("Failed to read the %s file.", conf)
                    return False

        return False

    def prepare_config_files(self, wrapper_path: str, build_dir: str) -> bool:
        """Prepare the necessary wrapper files for running the build.

        This method will return False if there is any errors happened during operation.

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
        return False

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
        return NoneDependencyAnalyzer()
