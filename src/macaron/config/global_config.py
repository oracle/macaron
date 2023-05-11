# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the GlobalConfig class to be used globally."""
import logging
import os
from dataclasses import dataclass, field

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class GlobalConfig:
    """Class for keeping track of global configurations."""

    expectation_paths: list[str] = field(default_factory=list)
    macaron_path: str = ""
    output_path: str = ""
    build_log_path: str = ""
    local_repos_path: str = ""
    gh_token: str = ""
    debug_level: int = logging.DEBUG
    resources_path: str = ""

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
                policy_file_path = os.path.join(exp_path, policy_path)
                if os.path.isfile(policy_file_path):
                    exp_files.append(policy_file_path)
                    logger.info("Added provenance expectation file %s", policy_file_path)
        elif os.path.isfile(exp_path):
            exp_files.append(exp_path)
            logger.info("Added provenance expectation file %s", exp_path)

        self.expectation_paths = exp_files


global_config = GlobalConfig()
"""The object that can be imported and used globally."""
