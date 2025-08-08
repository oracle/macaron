# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Gradle class which inherits BaseBuildTool.

This module is used to work with repositories that use Gradle build tool.
"""

import logging
import subprocess  # nosec B404

from macaron.config.defaults import defaults
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer, NoneDependencyAnalyzer
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists
from macaron.slsa_analyzer.build_tool.language import BuildLanguage

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

    def get_dep_analyzer(self) -> DependencyAnalyzer:
        """Create a DependencyAnalyzer for the Gradle build tool.

        Returns
        -------
        DependencyAnalyzer
            The DependencyAnalyzer object.

        Raises
        ------
        DependencyAnalyzerError
        """
        return NoneDependencyAnalyzer()

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
