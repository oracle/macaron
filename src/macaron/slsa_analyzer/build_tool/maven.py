# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Maven class which inherits BaseBuildTool.

This module is used to work with repositories that use Maven build tool.
"""

import logging
import os

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists
from macaron.slsa_analyzer.build_tool.language import BuildLanguage

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
