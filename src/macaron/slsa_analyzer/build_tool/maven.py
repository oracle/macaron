# Copyright (c) 2022 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Maven class which inherits BaseBuildTool.

This module is used to work with repositories that use Maven build tool.
"""

import logging
import os
from pathlib import Path

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.parsers.pomparser import extract_gav_from_pom, find_nearest_modules_pom
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
        super().load_defaults()
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

    def is_detected(
        self, repo_path: str, group_id: str | None = None, artifact_id: str | None = None
    ) -> list[tuple[str, float, str | None, str | None]]:
        """
        Return the list of build tools and their information used in the target repo.

        Parameters
        ----------
        repo_path : str
            The path to the target repo.
        group_id : str | None
            Optional Maven `groupId` used to refine detection (e.g., selecting the
            correct `pom.xml` when multiple are present). If ``None``, no filtering
            is applied.
        artifact_id : str | None
            Optional Maven `artifactId` used to refine detection. If ``None``, no
            filtering is applied.

        Returns
        -------
        list[tuple[str, float, str | None, str | None]]
            Tuples of ``(config_path, confidence_score, build_tool_version, parent_pom)``,
            where paths are relative to `repo_path` and `parent_pom` may be ``None``.
        """
        results: list[tuple[str, float, str | None, str | None]] = []
        confidence_score = 1.0

        if os.path.isfile(os.path.join(global_config.macaron_path, "pom.xml")):
            logger.error("Please remove pom.xml file in %s.", global_config.macaron_path)
            return []

        for config_name in self.build_configs:
            predicate_kwargs = {"group_id": group_id, "artifact_id": artifact_id}
            config_path = file_exists(
                repo_path,
                config_name,
                filters=self.path_filters,
                predicate=self.validate_pom_file,
                **predicate_kwargs,
            )
            if config_path:
                entrypoint_pom = find_nearest_modules_pom(config_path, repo_path)
                results.append((str(config_path.relative_to(repo_path)), confidence_score, None, entrypoint_pom))
                confidence_score = confidence_score / 2

        return results

    def validate_pom_file(self, config_path: Path, group_id: str | None = None, artifact_id: str | None = None) -> bool:
        """Validate a pom.xml file against an expected Maven G/A.

        This method is intended to be used as a lightweight filter when multiple
        candidate configuration files (e.g., `pom.xml`) are discovered. If both
        `group_id` and `artifact_id` are provided, the method extracts the
        ``(groupId, artifactId, version)`` from the POM at `config_path` and returns
        ``True`` only when the extracted group/artifact match the expected values.
        If either `group_id` or `artifact_id` is not provided, the method returns
        ``False``.

        Parameters
        ----------
        config_path : str
            Path to the candidate configuration file (typically a `pom.xml`).
        group_id : str or None, optional
            Expected Maven `groupId`. If ``None``, no match can be performed.
        artifact_id : str or None, optional
            Expected Maven `artifactId`. If ``None``, no match can be performed.

        Returns
        -------
        is_valid : bool
            ``True`` if `group_id` and `artifact_id` are provided and the POM at
            `config_path` contains matching values; otherwise ``False``.
        """
        if group_id and artifact_id:
            ex_group_id, ex_artifact_id, _ = extract_gav_from_pom(config_path)
            if group_id == ex_group_id and artifact_id == ex_artifact_id:
                return True
        return False
