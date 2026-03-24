# Copyright (c) 2023 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Docker class which inherits BaseBuildTool.

This module is used to work with repositories that use Docker as a build tool.
"""

from macaron.config.defaults import defaults
from macaron.database.table_definitions import Component
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists
from macaron.slsa_analyzer.build_tool.language import BuildLanguage


class Docker(BaseBuildTool):
    """This class contains the information of Docker when used as a build tool."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="docker", language=BuildLanguage.DOCKER, purl_type="docker")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        super().load_defaults()
        if "builder.docker" in defaults:
            for item in defaults["builder.docker"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("builder.docker", item))

        if "builder.docker.ci.deploy" in defaults:
            for item in defaults["builder.docker.ci.deploy"]:
                if item in self.ci_deploy_kws:
                    self.ci_deploy_kws[item] = defaults.get_list("builder.docker.ci.deploy", item)

    def is_detected(self, target: Component) -> list[tuple[str, float, str | None, str | None]]:
        """
        Return the list of build tools and their information used in the target repo.

        Parameters
        ----------
        target : Component
            The target software component.

        Returns
        -------
        list[tuple[str, float, str | None, str | None]]
            Tuples of ``(config_path, confidence_score, build_tool_version, parent_pom)``,
            where paths are relative to `repo_path` and `parent_pom` may be ``None``.
        """
        repo_path, _, _ = self.resolve_component_detection_target(target)
        if not repo_path:
            return []

        results: list[tuple[str, float, str | None, str | None]] = []
        confidence_score = 1.0
        for config_name in self.build_configs:
            if config_path := file_exists(repo_path, config_name, filters=self.path_filters):
                results.append((str(config_path.relative_to(repo_path)), confidence_score, None, None))
                confidence_score = confidence_score / 2
        return results
