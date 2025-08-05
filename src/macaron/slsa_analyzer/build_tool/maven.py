# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Maven class which inherits BaseBuildTool.

This module is used to work with repositories that use Maven build tool.
"""

import logging
import os

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer, DependencyAnalyzerError, DependencyTools
from macaron.dependency_analyzer.cyclonedx_mvn import CycloneDxMaven
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from macaron.util import copy_file_bulk

logger: logging.Logger = logging.getLogger(__name__)


class Maven(BaseBuildTool):
    """This class contains the information of the Maven build tool."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="maven", language=BuildLanguage.JAVA, purl_type="maven")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        if "builder.maven" in defaults:
            for item in defaults["builder.maven"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("builder.maven", item))

        if "builder.maven.ci.build" in defaults:
            for item in defaults["builder.maven.ci.build"]:
                if item in self.ci_build_kws:
                    self.ci_build_kws[item] = defaults.get_list("builder.maven.ci.build", item)

        if "builder.maven.ci.deploy" in defaults:
            for item in defaults["builder.maven.ci.deploy"]:
                if item in self.ci_deploy_kws:
                    self.ci_deploy_kws[item] = defaults.get_list("builder.maven.ci.deploy", item)

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
        # The repo path can be pointed to the same directory as the macaron root path.
        # However, there shouldn't be any pom.xml in the macaron root path.
        if os.path.isfile(os.path.join(global_config.macaron_path, "pom.xml")):
            logger.error(
                "Please remove pom.xml file in %s.",
                global_config.macaron_path,
            )
            return False
        maven_config_files = self.build_configs
        return any(file_exists(repo_path, file) for file in maven_config_files)

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
            # Ensure that mvnw is executable.
            file_path = os.path.join(build_dir, "mvnw")
            status = os.stat(file_path)
            if oct(status.st_mode)[-3:] != "744":
                logger.debug("%s does not have 744 permission. Changing it to 744.")
                os.chmod(file_path, 0o744)
            return True

        return False

    def get_dep_analyzer(self) -> CycloneDxMaven:
        """
        Create a DependencyAnalyzer for the Maven build tool.

        Returns
        -------
        CycloneDxMaven
            The CycloneDxMaven object.

        Raises
        ------
        DependencyAnalyzerError
        """
        if "dependency.resolver" not in defaults or "dep_tool_maven" not in defaults["dependency.resolver"]:
            raise DependencyAnalyzerError("No default dependency analyzer is found.")
        if not DependencyAnalyzer.tool_valid(defaults.get("dependency.resolver", "dep_tool_maven")):
            raise DependencyAnalyzerError(
                f"Dependency analyzer {defaults.get('dependency.resolver', 'dep_tool_maven')} is not valid.",
            )

        tool_name, tool_version = tuple(
            defaults.get(
                "dependency.resolver",
                "dep_tool_maven",
                fallback="cyclonedx-maven:2.6.2",
            ).split(":")
        )
        if tool_name == DependencyTools.CYCLONEDX_MAVEN:
            return CycloneDxMaven(
                resources_path=global_config.resources_path,
                file_name="bom.json",
                tool_name=tool_name,
                tool_version=tool_version,
            )

        raise DependencyAnalyzerError(f"Unsupported SBOM generator for Maven: {tool_name}.")
