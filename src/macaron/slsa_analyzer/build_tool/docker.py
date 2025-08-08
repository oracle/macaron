# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Docker class which inherits BaseBuildTool.

This module is used to work with repositories that use Docker as a build tool.
"""

from macaron.config.defaults import defaults
from macaron.dependency_analyzer.cyclonedx import NoneDependencyAnalyzer
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists
from macaron.slsa_analyzer.build_tool.language import BuildLanguage


class Docker(BaseBuildTool):
    """This class contains the information of Docker when used as a build tool."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="docker", language=BuildLanguage.DOCKER, purl_type="docker")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        if "builder.docker" in defaults:
            for item in defaults["builder.docker"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("builder.docker", item))

        if "builder.docker.ci.deploy" in defaults:
            for item in defaults["builder.docker.ci.deploy"]:
                if item in self.ci_deploy_kws:
                    self.ci_deploy_kws[item] = defaults.get_list("builder.docker.ci.deploy", item)

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
        return any(file_exists(repo_path, file) for file in self.build_configs)

    def get_dep_analyzer(self) -> NoneDependencyAnalyzer:
        """Create a DependencyAnalyzer for the Docker build tool. Currently unimplemented.

        Returns
        -------
        NoneDependencyAnalyser
            The NoneDependencyAnalyser object.

        Raises
        ------
        DependencyAnalyzerError
        """
        # TODO: Find a suitable tool to analyse dependencies; as of now Syft
        #       seems to be a good option, but need to experiment.
        return NoneDependencyAnalyzer()
