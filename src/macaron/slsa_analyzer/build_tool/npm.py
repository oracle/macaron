# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the NPM class which inherits BaseBuildTool.

This module is used to work with repositories that use npm/pnpm as its
build tool.
"""

import logging
import os

from macaron.config.defaults import defaults
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer, NoneDependencyAnalyzer
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, BuildToolCommand, file_exists
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from macaron.slsa_analyzer.checks.check_result import Confidence

logger: logging.Logger = logging.getLogger(__name__)


class NPM(BaseBuildTool):
    """This class contains the information of the npm/pnpm build tool."""

    def __init__(self) -> None:
        super().__init__(name="npm", language=BuildLanguage.JAVASCRIPT, purl_type="npm")
        # The run sub-commands is also accepted and takes its own build and deploy arguments.
        self.build_run_arg: list[str] = []
        self.deploy_run_arg: list[str] = []

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
        return any(file_exists(repo_path, file) for file in npm_config_files)

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

    def get_dep_analyzer(self) -> DependencyAnalyzer:
        """Create a DependencyAnalyzer for the build tool.

        Returns
        -------
        DependencyAnalyzer
            The DependencyAnalyzer object.
        """
        # TODO: Implement this method.
        return NoneDependencyAnalyzer()

    def is_deploy_command(
        self, cmd: BuildToolCommand, excluded_configs: list[str] | None = None
    ) -> tuple[bool, Confidence]:
        """
        Determine if the command is a deploy command.

        A deploy command usually performs multiple tasks, such as compilation, packaging, and publishing the artifact.
        This function filters the build tool commands that are called from the configuration files provided as input.

        Parameters
        ----------
        cmd: BuildToolCommand
            The build tool command object.
        excluded_configs: list[str] | None
            Build tool commands that are called from these configuration files are excluded.

        Returns
        -------
        tuple[bool, Confidence]
            Return True along with the inferred confidence level if the command is a deploy tool command.
        """
        # Check the language.
        if cmd["language"] is not self.language:
            return False, Confidence.HIGH

        build_cmd = cmd["command"]
        cmd_program_name = os.path.basename(build_cmd[0])

        # Some projects use a publisher tool and some use the build tool with deploy arguments.
        deploy_tools = self.publisher if self.publisher else self.builder
        deploy_args = self.deploy_arg

        # Sometimes npm commands use the `run` sub-command:
        # e.g., `npm run publish`.
        if cmd_program_name in deploy_tools and len(build_cmd) > 2 and build_cmd[1] == "run":
            # Use the deploy run args that follow the `run` sub-command.
            deploy_args = self.deploy_run_arg

        if not self.match_cmd_args(cmd=cmd["command"], tools=deploy_tools, args=deploy_args):
            return False, Confidence.HIGH

        # Check if the CI workflow is a configuration for a known tool.
        if excluded_configs and os.path.basename(cmd["ci_path"]) in excluded_configs:
            return False, Confidence.HIGH

        return True, self.infer_confidence_deploy_command(cmd)

    def is_package_command(
        self, cmd: BuildToolCommand, excluded_configs: list[str] | None = None
    ) -> tuple[bool, Confidence]:
        """
        Determine if the command is a packaging command.

        A packaging command usually performs multiple tasks, such as compilation and creating the artifact.
        This function filters the build tool commands that are called from the configuration files provided as input.

        Parameters
        ----------
        cmd: BuildToolCommand
            The build tool command object.
        excluded_configs: list[str] | None
            Build tool commands that are called from these configuration files are excluded.

        Returns
        -------
        tuple[bool, Confidence]
            Return True along with the inferred confidence level if the command is a build tool command.
        """
        # Check the language.
        if cmd["language"] is not self.language:
            return False, Confidence.HIGH

        build_cmd = cmd["command"]
        cmd_program_name = os.path.basename(build_cmd[0])
        if not cmd_program_name:
            return False, Confidence.HIGH

        builder = self.packager if self.packager else self.builder
        build_args = self.build_arg

        # Sometimes npm commands use the `run` sub-command:
        # e.g., `npm run build`.
        if cmd_program_name in builder and len(build_cmd) > 2 and build_cmd[1] == "run":
            # Use the build run args that follow the `run` sub-command.
            build_args = self.build_run_arg

        if not self.match_cmd_args(cmd=cmd["command"], tools=builder, args=build_args):
            return False, Confidence.HIGH

        # Check if the CI workflow is a configuration for a known tool.
        if excluded_configs and os.path.basename(cmd["ci_path"]) in excluded_configs:
            return False, Confidence.HIGH

        return True, Confidence.HIGH
