# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Poetry class which inherits BaseBuildTool.

This module is used to work with repositories that use Poetry for dependency management.
"""

import logging
import os

from cyclonedx_py import __version__ as cyclonedx_version

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer
from macaron.dependency_analyzer.cyclonedx_python import CycloneDxPython
from macaron.slsa_analyzer.build_tool import pyproject
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, BuildToolCommand, file_exists
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from macaron.slsa_analyzer.checks.check_result import Confidence

logger: logging.Logger = logging.getLogger(__name__)


class Poetry(BaseBuildTool):
    """This class contains the information of the poetry build tool."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="poetry", language=BuildLanguage.PYTHON, purl_type="pypi")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        super().load_defaults()
        if "builder.poetry" in defaults:
            for item in defaults["builder.poetry"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("builder.poetry", item))

        if "builder.pip.ci.deploy" in defaults:
            for item in defaults["builder.poetry.ci.deploy"]:
                if item in self.ci_deploy_kws:
                    self.ci_deploy_kws[item] = defaults.get_list("builder.poetry.ci.deploy", item)

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
            if file_exists(repo_path, file, filters=self.path_filters):
                package_lock_exists = file
                break

        file_paths = (file_exists(repo_path, file, filters=self.path_filters) for file in self.build_configs)
        for config_path in file_paths:
            if config_path and os.path.basename(config_path) == "pyproject.toml":
                if package_lock_exists:
                    return True
                if pyproject.contains_build_tool("poetry", config_path):
                    return True
                # Check the build-system section.
                for tool in self.build_requires + self.build_backend:
                    if pyproject.build_system_contains_tool(tool, config_path):
                        return True

        return False

    def get_dep_analyzer(self) -> DependencyAnalyzer:
        """Create a DependencyAnalyzer for the build tool.

        Returns
        -------
        DependencyAnalyzer
            The DependencyAnalyzer object.
        """
        return CycloneDxPython(
            resources_path=global_config.resources_path,
            file_name="python_sbom.json",
            tool_name="cyclonedx_py",
            tool_version=cyclonedx_version,
        )

    def is_deploy_command(
        self, cmd: BuildToolCommand, excluded_configs: list[str] | None = None, provenance_workflow: str | None = None
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
        provenance_workflow: str | None
            The relative path to the root CI file that is captured in a provenance or None if provenance is not found.

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

        # Sometimes poetry is called as a Python module.
        if cmd_program_name in self.interpreter and len(build_cmd) > 2 and build_cmd[1] in self.interpreter_flag:
            # Use the module cmd-line args.
            build_cmd = build_cmd[2:]

        if not self.match_cmd_args(cmd=build_cmd, tools=deploy_tools, args=deploy_args):
            return False, Confidence.HIGH

        # Check if the CI workflow is a configuration for a known tool.
        if excluded_configs and os.path.basename(cmd["ci_path"]) in excluded_configs:
            return False, Confidence.HIGH

        return True, self.infer_confidence_deploy_command(cmd, provenance_workflow)

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

        # Sometimes poetry is called as a Python module.
        if cmd_program_name in self.interpreter and len(build_cmd) > 2 and build_cmd[1] in self.interpreter_flag:
            # Use the module cmd-line args.
            build_cmd = build_cmd[2:]

        if not self.match_cmd_args(cmd=build_cmd, tools=builder, args=build_args):
            return False, Confidence.HIGH

        # Check if the CI workflow is a configuration for a known tool.
        if excluded_configs and os.path.basename(cmd["ci_path"]) in excluded_configs:
            return False, Confidence.HIGH

        return True, Confidence.HIGH
