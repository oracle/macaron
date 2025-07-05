# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Gradle class which inherits BaseBuildTool.

This module is used to work with repositories that use Gradle build tool.
"""

import logging
import os
import subprocess  # nosec B404

import macaron
from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer, DependencyAnalyzerError, DependencyTools
from macaron.dependency_analyzer.cyclonedx_gradle import CycloneDxGradle
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from macaron.util import copy_file_bulk

logger: logging.Logger = logging.getLogger(__name__)


class Gradle(BaseBuildTool):
    """This class contains the information of the Gradle build tool."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="gradle", language=BuildLanguage.JAVA, purl_type="maven")

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

        if "builder.gradle.runtime" in defaults:
            try:
                self.runtime_options.build_timeout = defaults.getfloat(
                    "builder.gradle.runtime", "build_timeout", fallback=self.runtime_options.build_timeout
                )
            except ValueError as error:
                logger.error(
                    "Failed to validate builder.gradle.runtime.build_timeout in defaults.ini. "
                    "Falling back to the default build timeout %s seconds: %s",
                    self.runtime_options.build_timeout,
                    error,
                )

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
        return any(file_exists(repo_path, file) for file in gradle_config_files)

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

    def get_dep_analyzer(self) -> CycloneDxGradle:
        """Create a DependencyAnalyzer for the Gradle build tool.

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
                f"Dependency analyzer {defaults.get('dependency.resolver', 'dep_tool_gradle')} is not valid.",
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
            )

        raise DependencyAnalyzerError(f"Unsupported SBOM generator for Gradle: {tool_name}.")

    def get_gradle_exec(self, repo_path: str) -> str:
        """Get the Gradle executable for the repo.

        Parameters
        ----------
        repo_path: str
            The absolute path to a repository containing Gradle projects.

        Returns
        -------
        str
            The absolute path to the Gradle executable.
        """
        # We try to use the gradlew that comes with the repository first.
        repo_gradlew = os.path.join(repo_path, "gradlew")
        if os.path.isfile(repo_gradlew) and os.access(repo_gradlew, os.X_OK):
            return repo_gradlew

        # We use Macaron's built-in gradlew as a fallback option.
        return os.path.join(os.path.join(macaron.MACARON_PATH, "resources"), "gradlew")

    def get_group_id(self, gradle_exec: str, project_path: str) -> str | None:
        """Get the group id of a Gradle project.

        A Gradle project is a directory containing a ``build.gradle`` file.
        According to the Gradle's documentation, there is a one-to-one mapping between
        a "project" and a ``build.gradle`` file.
        See: https://docs.gradle.org/current/javadoc/org/gradle/api/Project.html.

        Parameters
        ----------
        gradle_exec: str
            The absolute path to the Gradle executable.

        project_path : str
            The absolute path to the Gradle project.

        Returns
        -------
        str | None
            The group id of the project, if exists.
        """
        try:
            logger.info(
                "Identifying the group ID for the artifact. This can take a while if Gradle needs to be downloaded."
            )
            result = subprocess.run(  # nosec B603
                [gradle_exec, "properties"],
                capture_output=True,
                cwd=project_path,
                check=False,
                timeout=self.runtime_options.build_timeout,
            )
        except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as error:
            logger.debug("Could not capture the group id of the Gradle project at %s", project_path)
            logger.debug("Error: %s", error)
            return None

        if result.returncode == 0:
            lines = result.stdout.decode().split("\n")
            for line in lines:
                if line.startswith("group: "):
                    group = line.replace("group: ", "")
                    # The value of group here can be an empty string.
                    if group:
                        return group
                    break

        logger.debug("Could not capture the group id of the repo at %s", project_path)
        logger.debug("Stderr:\n%s", result.stderr)
        return None
