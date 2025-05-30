# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the GlobalConfig class to be used globally."""
import logging
import os
from dataclasses import dataclass, field

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class GlobalConfig:
    """Class for keeping track of global configurations."""

    #: The provenance expectation paths.
    expectation_paths: list[str] = field(default_factory=list)

    #: The path to the Macaron Python package.
    macaron_path: str = ""

    #: The path to the output files.
    output_path: str = ""

    #: The path to build logs directory.
    build_log_path: str = ""

    #: The path to the local clone of the target repository.
    local_repos_path: str = ""

    #: The GitHub token.
    gh_token: str = ""

    #: The GitLab public token.
    gl_token: str = ""

    #: The GitLab self-hosted token.
    gl_self_host_token: str = ""

    #: The debug level.
    debug_level: int = logging.DEBUG

    #: The path to resources directory.
    resources_path: str = ""

    #: The path to Python virtual environment.
    python_venv_path: str = ""

    #: The path to the local .m2 Maven repository. This attribute is None if there is no available .m2 directory.
    local_maven_repo: str | None = None

    def load(
        self,
        macaron_path: str,
        output_path: str,
        build_log_path: str,
        debug_level: int,
        local_repos_path: str,
        resources_path: str,
    ) -> None:
        """Initiate the GlobalConfig object.

        Parameters
        ----------
        macaron_path : str
            Macaron's root path.
        output_path : str
            Output path.
        build_log_path : str
            The build log path.
        debug_level : int
            The global debug level.
        local_repos_path : str
            The directory to look for local repositories.
        resources_path : str
            The path to the resources files needed for the analysis (i.e. mvnw, gradlew, etc.)
        """
        self.macaron_path = macaron_path
        self.output_path = output_path
        self.build_log_path = build_log_path
        self.debug_level = debug_level
        self.local_repos_path = local_repos_path
        self.resources_path = resources_path

    def load_expectation_files(self, exp_path: str) -> None:
        """
        Load provenance expectation files.

        Parameters
        ----------
        exp_path : str
            The path to the provenance expectation file or directory containing the files.
        """
        exp_files = []
        if os.path.isdir(exp_path):
            for policy_path in os.listdir(exp_path):
                policy_file_path = os.path.abspath(os.path.join(exp_path, policy_path))
                if os.path.isfile(policy_file_path):
                    exp_files.append(policy_file_path)
                    logger.info("Added provenance expectation file %s", os.path.relpath(policy_file_path, os.getcwd()))
        elif os.path.isfile(exp_path):
            exp_files.append(os.path.abspath(exp_path))
            logger.info("Added provenance expectation file %s", os.path.relpath(exp_path, os.getcwd()))

        self.expectation_paths = exp_files

    def load_python_venv(self, venv_path: str) -> None:
        """
        Load Python virtual environment.

        Parameters
        ----------
        venv_path : str
            The path to the Python virtual environment of the target software component.
        """
        if os.path.isdir(venv_path):
            logger.info(
                "Found Python virtual environment for the analysis target at %s",
                os.path.relpath(venv_path, os.getcwd()),
            )

        self.python_venv_path = str(os.path.abspath(venv_path))


global_config = GlobalConfig()
"""The object that can be imported and used globally."""
