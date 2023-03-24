# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Poetry class which inherits BaseBuildTool.

This module is used to work with repositories that use Poetry for dependency management.
"""

import glob
import logging
import os
import tomllib
from collections.abc import Iterable
from pathlib import Path

from macaron.config.defaults import defaults
from macaron.dependency_analyzer import DependencyAnalyzer, NoneDependencyAnalyzer
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists

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
        package_lock_exists = ""
        for file in self.package_lock:
            if file_exists(repo_path, file):
                package_lock_exists = file
                break

        for conf in self.build_configs:
            # Find the paths of all pyproject.toml files.
            pattern = os.path.join(repo_path, "**", conf)
            files_detected = glob.glob(pattern, recursive=True)

            if files_detected:
                # If a package_lock file exists, and a config file is present, Poetry build tool is detected.
                if package_lock_exists:
                    return True
                # TODO: this implementation assumes one build type, so when multiple build types are supported, this
                # needs to be updated.
                # Take the highest level file, if there are two at the same level, take the first in the list.
                file_path = min(files_detected, key=lambda x: len(Path(x).parts))
                try:
                    # Parse the .toml file
                    with open(file_path, "rb") as toml_file:
                        try:
                            data = tomllib.load(toml_file)
                            # Check for the existence of a [tool.poetry] section.
                            if ("tool" in data) and ("poetry" in data["tool"]):
                                return True
                        except tomllib.TOMLDecodeError:
                            logger.error("Failed to read the %s file: invalid toml file.", conf)
                            return False
                    return False
                except FileNotFoundError:
                    logger.error("Failed to read the %s file.", conf)
                    return False

        return False

    def prepare_config_files(self, wrapper_path: str, build_dir: str) -> bool:
        """Prepare the necessary wrapper files for running the build.

        This method returns False on errors. Poetry doesn't require any preparation, therefore this method always
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
            True if succeeds else False.
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

    def get_build_dirs(self, repo_path: str) -> Iterable[Path]:
        """Find directories in the repository that have their own build scripts.

        This is especially important for applications that consist of multiple services.

        Parameters
        ----------
        repo_path: str
            The path to the target repo.

        Yields
        ------
        Path
            The relative paths from the repo path that contain build scripts.
        """
        config_paths: set[str] = set()
        config_files = self.build_configs + self.package_lock
        for build_cfg in config_files:
            config_paths.update(glob.glob(os.path.join(repo_path, "**", build_cfg), recursive=True))

        list_iter = iter(sorted(config_paths, key=lambda x: (str(Path(x).parent), len(Path(x).parts))))
        try:
            cfg_path = next(list_iter)
            yield Path(cfg_path).parent.relative_to(repo_path)
            while next_item := next(list_iter):
                if str(Path(cfg_path).parent) in next_item:
                    continue
                cfg_path = next_item
                yield Path(next_item).parent.relative_to(repo_path)

        except StopIteration:
            pass
