# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Go class which inherits BaseBuildTool.

This module is used to work with repositories that have Go.
"""

from macaron.config.defaults import defaults
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, file_exists
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

    def is_detected(
        self, repo_path: str, groupID: str | None = None, artifactID: str | None = None
    ) -> list[tuple[str, float, str | None, str | None]]:
        """
        Return the list of build tools and their information used in the target repo.

        Parameters
        ----------
        repo_path : str
            The path to the target repo.
        groupID : str | None
            Optional Maven `groupId` used to refine detection (e.g., selecting the
            correct `pom.xml` when multiple are present). If ``None``, no filtering
            is applied.
        artifactID : str | None
            Optional Maven `artifactId` used to refine detection. If ``None``, no
            filtering is applied.

        Returns
        -------
        list[tuple[str, float, str | None, str | None]]
            Tuples of ``(config_path, confidence_score, build_tool_version, parent_pom)``,
            where paths are relative to `repo_path` and `parent_pom` may be ``None``.
        """
        go_config_files = self.build_configs + self.entry_conf
        return any(file_exists(repo_path, file, filters=self.path_filters) for file in go_config_files)
