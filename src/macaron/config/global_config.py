# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the GlobalConfig class to be used globally."""
import logging
import os
from dataclasses import dataclass

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class GlobalConfig:
    """Class for keeping track of global configurations."""

    policy_paths: list[str]
    artifact_repositories: list[str]
    macaron_path: str = ""
    output_path: str = ""
    build_log_path: str = ""
    local_repos_path: str = ""
    gh_token: str = ""
    debug_level: int = logging.DEBUG
    resources_path: str = ""

    def __init__(self) -> None:
        self.policy_paths = []
        self.artifact_repositories = []

    def load(
        self,
        macaron_path: str,
        output_path: str,
        build_log_path: str,
        debug_level: int,
        local_repos_path: str,
        gh_token: str,
        policy_paths: list[str],
        resources_path: str,
        artifact_repositories: list[str],
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
        gh_token : str
            The GitHub personal access token.
        policy_paths : str
            The path to the policy file.
        resources_path : str
            The path to the resources files needed for the analysis (i.e. mvnw, gradlew, etc.)
        artifact_repositories : list[str]
            The list of repositories to search for artifact POMs in (e.g. Maven central)
        """
        self.macaron_path = macaron_path
        self.output_path = output_path
        self.build_log_path = build_log_path
        self.debug_level = debug_level
        self.local_repos_path = local_repos_path
        self.gh_token = gh_token
        self.resources_path = resources_path
        self.artifact_repositories = artifact_repositories

        # Find the policies.
        policy_files = []
        for policy_path in policy_paths:
            if os.path.isdir(policy_path):
                for policy_file_path in os.listdir(policy_path):
                    if os.path.isfile(policy_file_path):
                        policy_files.append(policy_file_path)
                        logger.info("Added policy file %s", policy_file_path)
            elif os.path.isfile(policy_path):
                policy_files.append(policy_path)
                logger.info("Added policy file %s", policy_path)

        self.policy_paths = policy_files


global_config = GlobalConfig()
"""The object that can be imported and used globally."""
