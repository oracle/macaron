# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the GlobalConfig class to be used globally."""

import logging
from dataclasses import dataclass

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class GlobalConfig:
    """Class for keeping track of global configurations."""

    macaron_path: str = ""
    output_path: str = ""
    build_log_path: str = ""
    local_repos_path: str = ""
    gh_token: str = ""
    debug_level: int = logging.DEBUG
    policy_path: str = ""
    resources_path: str = ""

    def load(
        self,
        macaron_path: str,
        output_path: str,
        build_log_path: str,
        debug_level: int,
        local_repos_path: str,
        gh_token: str,
        policy_path: str,
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
        gh_token : str
            The GitHub personal access token.
        policy_path : str
            The path to the policy file.
        resources_path : str
            The path to the resources files needed for the analysis (i.e. mvnw, gradlew, etc.)
        """
        self.macaron_path = macaron_path
        self.output_path = output_path
        self.build_log_path = build_log_path
        self.debug_level = debug_level
        self.local_repos_path = local_repos_path
        self.gh_token = gh_token
        self.policy_path = policy_path
        self.resources_path = resources_path


global_config = GlobalConfig()
"""The object that can be imported and used globally."""
