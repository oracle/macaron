# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Gradle class which inherits BaseBuildTool.

This module is used to work with repositories that use Gradle build tool.
"""

import glob
import logging
import os
from pathlib import Path

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.dependency_analyzer import DependencyAnalyzer, DependencyAnalyzerError, DependencyTools
from macaron.dependency_analyzer.cyclonedx_gradle import CycloneDxGradle
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists
from macaron.util import copy_file_bulk

logger: logging.Logger = logging.getLogger(__name__)


class Gradle(BaseBuildTool):
    """This class contains the information of the Gradle build tool."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="gradle")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        if "builder.gradle" in defaults:
            for item in defaults["builder.gradle"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("builder.gradle", item))

        if "builder.gradle.ci.build" in defaults:
            for item in defaults["builder.gradle.ci.build"]:
                if item in self.ci_build_kws:
                    self.ci_build_kws[item] = defaults.get_list("builder.gradle.ci.build", item)

        if "builder.gradle.ci.deploy" in defaults:
            for item in defaults["builder.gradle.ci.deploy"]:
                if item in self.ci_deploy_kws:
                    self.ci_deploy_kws[item] = defaults.get_list("builder.gradle.ci.deploy", item)

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
        gradle_config_files = self.build_configs + self.entry_conf
        for file in gradle_config_files:
            if file_exists(repo_path, file):
                return True

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
        # The path of the needed wrapper files
        wrapper_files = self.wrapper_files

        if copy_file_bulk(wrapper_files, wrapper_path, build_dir):
            # Ensure that gradlew is executable.
            file_path = os.path.join(build_dir, "gradlew")
            status = os.stat(file_path)
            if oct(status.st_mode)[-3:] != "744":
                logger.debug("%s does not have 744 permission. Changing it to 744.")
                os.chmod(file_path, 0o744)
            return True

        return False

    def get_dep_analyzer(self, repo_path: str) -> CycloneDxGradle:
        """Create a DependencyAnalyzer for the Gradle build tool.

        Parameters
        ----------
        repo_path: str
            The path to the target repo.

        Returns
        -------
        CycloneDxGradle
            The CycloneDxGradle object.

        Raises
        ------
        DependencyAnalyzerError
        """
        if "dependency.resolver" not in defaults or "dep_tool_gradle" not in defaults["dependency.resolver"]:
            raise DependencyAnalyzerError("No default dependency analyzer is found.")
        if not DependencyAnalyzer.tool_valid(defaults.get("dependency.resolver", "dep_tool_gradle")):
            raise DependencyAnalyzerError(
                f"Dependency analyzer {defaults.get('dependency.resolver','dep_tool_gradle')} is not valid.",
            )

        tool_name, tool_version = tuple(
            defaults.get(
                "dependency.resolver",
                "dep_tool_gradle",
                fallback="cyclonedx-gradle:1.7.3",
            ).split(":")
        )
        if tool_name == DependencyTools.CYCLONEDX_GRADLE:
            return CycloneDxGradle(
                resources_path=global_config.resources_path,
                file_name="bom.json",
                tool_name=tool_name,
                tool_version=tool_version,
                repo_path=repo_path,
            )

        raise DependencyAnalyzerError(f"Unsupported SBOM generator for Gradle: {tool_name}.")

    def get_build_dirs(self, repo_path: str) -> set[Path]:
        """Find directories in the repository that have their own build scripts.

        This is especially important for applications that consist of multiple services.

        Parameters
        ----------
        repo_path: str
            The path to the target repo.

        Returns
        -------
        set[Path]
            The list of paths that contain build scripts.
        """
        config_paths: set[str] = set()
        for build_cfg in self.build_configs:
            config_paths.update(glob.glob(os.path.join(repo_path, "**", build_cfg), recursive=True))

        return {Path(path).parent for path in config_paths}
