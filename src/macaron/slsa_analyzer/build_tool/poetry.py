# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Poetry class which inherits BaseBuildTool.

This module is used to work with repositories that use Poetry for dependency management.
"""

import glob
import logging
import os
import tomllib
from pathlib import Path

from cyclonedx_py import __version__ as cyclonedx_version

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer
from macaron.dependency_analyzer.cyclonedx_python import CycloneDxPython
from macaron.errors import DependencyAnalyzerError
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

    def get_dep_analyzer(self) -> DependencyAnalyzer:
        """Create a DependencyAnalyzer for the build tool.

        Returns
        -------
        DependencyAnalyzer
            The DependencyAnalyzer object.
        """
        tool_name = "cyclonedx_py"
        if not DependencyAnalyzer.tool_valid(f"{tool_name}:{cyclonedx_version}"):
            raise DependencyAnalyzerError(
                f"Dependency analyzer {defaults.get('dependency.resolver','dep_tool_gradle')} is not valid.",
            )
        return CycloneDxPython(
            resources_path=global_config.resources_path,
            file_name="python_sbom.json",
            tool_name=tool_name,
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
