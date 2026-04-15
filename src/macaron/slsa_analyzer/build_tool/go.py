# Copyright (c) 2023 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Go class which inherits BaseBuildTool.

This module is used to work with repositories that have Go.
"""

from macaron.config.defaults import defaults
from macaron.database.table_definitions import Component
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, BuildToolConfig, file_exists
from macaron.slsa_analyzer.build_tool.language import BuildLanguage


class Go(BaseBuildTool):
    """This class contains the information of the Go build tool."""

    def __init__(self) -> None:
        super().__init__(name="go", language=BuildLanguage.GO, purl_type="golang")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        super().load_defaults()
        if "builder.go" in defaults:
            for item in defaults["builder.go"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("builder.go", item))

        if "builder.go.ci.deploy" in defaults:
            for item in defaults["builder.go.ci.deploy"]:
                if item in self.ci_deploy_kws:
                    self.ci_deploy_kws[item] = defaults.get_list("builder.go.ci.deploy", item)

    def is_detected(self, target: Component) -> list[BuildToolConfig]:
        """
        Return the list of build tools and their information used in the target repo.

        Parameters
        ----------
        target : Component
            The target software component.

        Returns
        -------
        list[BuildToolConfig]
            See ``BuildToolConfig`` in ``base_build_tool.py`` for field definitions.
        """
        repo_path, _, _ = self.resolve_component_detection_target(target)
        if not repo_path:
            return []

        go_config_files = self.build_configs + self.entry_conf
        results: list[BuildToolConfig] = []
        confidence_score = 1.0
        for config_name in go_config_files:
            if config_path := file_exists(repo_path, config_name, filters=self.path_filters):
                results.append((str(config_path.relative_to(repo_path)), confidence_score, None, None))
                confidence_score = confidence_score / 2
        return results
