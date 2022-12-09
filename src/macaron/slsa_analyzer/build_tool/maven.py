# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Maven class which inherits BaseBuildTool.

This module is used to work with repositories that use Maven build tool.
"""

import logging
import os

from macaron.config.defaults import defaults
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists
from macaron.util import copy_file_bulk

logger: logging.Logger = logging.getLogger(__name__)


class Maven(BaseBuildTool):
    """This class contains the information of the Maven build tool."""

    def __init__(self) -> None:
        super().__init__(name="maven")

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
        maven_config_files = self.build_configs
        for file in maven_config_files:
            if file_exists(repo_path, file):
                return True

        return False

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
            # Ensure that mvnw is executable.
            file_path = os.path.join(build_dir, "mvnw")
            status = os.stat(file_path)
            if oct(status.st_mode)[-3:] != "744":
                logger.debug("%s does not have 744 permission. Changing it to 744.")
                os.chmod(file_path, 0o744)
            return True

        return False
