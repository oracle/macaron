# Copyright (c) 2022 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Gradle class which inherits BaseBuildTool.

This module is used to work with repositories that use Gradle build tool.
"""

import logging
import subprocess  # nosec B404
from pathlib import Path

from macaron.config.defaults import defaults
from macaron.database.table_definitions import Component
from macaron.parsers.gradleparser import (
    extract_gav_from_gradle_project,
    extract_included_gradle_modules,
    find_matching_gradle_module_build_configs,
    find_nearest_modules_gradle_config,
)
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, BuildToolConfig, file_exists
from macaron.slsa_analyzer.build_tool.language import BuildLanguage

logger: logging.Logger = logging.getLogger(__name__)


class Gradle(BaseBuildTool):
    """This class contains the information of the Gradle build tool."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="gradle", language=BuildLanguage.JAVA, purl_type="maven")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        super().load_defaults()
        if "builder.gradle" in defaults:
            for item in defaults["builder.gradle"]:
                if hasattr(self, item):
                    setattr(self, item, defaults.get_list("builder.gradle", item))

        if "builder.gradle.ci.build" in defaults:
            for item in defaults["builder.gradle.ci.build"]:
                if item in self.ci_build_kws:
                    self.ci_build_kws[item] = defaults.get_list("builder.gradle.ci.build", item)

        if "builder.gradle.ci.deploy" in defaults:
            for item in defaults["builder.gradle.ci.deploy"]:
                if item in self.ci_deploy_kws:
                    self.ci_deploy_kws[item] = defaults.get_list("builder.gradle.ci.deploy", item)

        if "builder.gradle.runtime" in defaults:
            try:
                self.runtime_options.build_timeout = defaults.getfloat(
                    "builder.gradle.runtime", "build_timeout", fallback=self.runtime_options.build_timeout
                )
            except ValueError as error:
                logger.error(
                    "Failed to validate builder.gradle.runtime.build_timeout in defaults.ini. "
                    "Falling back to the default build timeout %s seconds: %s",
                    self.runtime_options.build_timeout,
                    error,
                )

    def is_detected(
        self,
        target: Component,
    ) -> list[BuildToolConfig]:
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
        repo_path, group_id, artifact_id = self.resolve_component_detection_target(target)
        if not repo_path:
            return []

        results: list[BuildToolConfig] = []
        confidence_score = 1.0
        gradle_config_files = self.build_configs + self.entry_conf
        seen_paths: set[Path] = set()

        # Prioritize module-level build configs for multi-module artifacts.
        if artifact_id:
            for module_config_path in find_matching_gradle_module_build_configs(Path(repo_path), artifact_id):
                if module_config_path in seen_paths:
                    continue
                if self.validate_gradle_file(
                    module_config_path,
                    group_id=group_id,
                    artifact_id=artifact_id,
                    repo_path=repo_path,
                ):
                    entrypoint_gradle = find_nearest_modules_gradle_config(module_config_path, repo_path)
                    results.append(
                        (str(module_config_path.relative_to(repo_path)), confidence_score, None, entrypoint_gradle)
                    )
                    seen_paths.add(module_config_path)
                    confidence_score = confidence_score / 2

        for config_name in gradle_config_files:
            predicate_kwargs = {"group_id": group_id, "artifact_id": artifact_id}
            config_path = file_exists(
                repo_path,
                config_name,
                filters=self.path_filters,
                predicate=self.validate_gradle_file,
                **predicate_kwargs,
            )
            if config_path and config_path not in seen_paths:
                entrypoint_gradle = find_nearest_modules_gradle_config(config_path, repo_path)
                results.append((str(config_path.relative_to(repo_path)), confidence_score, None, entrypoint_gradle))
                seen_paths.add(config_path)
                confidence_score = confidence_score / 2

        # Fallback: if strict coordinate validation cannot find a config, return
        # existing Gradle config files with lower confidence.
        if not results:
            fallback_confidence = 0.1
            for config_name in gradle_config_files:
                config_path = file_exists(
                    repo_path,
                    config_name,
                    filters=self.path_filters,
                    predicate=None,
                )
                if not config_path:
                    continue
                if config_path in seen_paths:
                    continue
                entrypoint_gradle = find_nearest_modules_gradle_config(config_path, repo_path)
                results.append((str(config_path.relative_to(repo_path)), fallback_confidence, None, entrypoint_gradle))
                seen_paths.add(config_path)
                fallback_confidence = fallback_confidence / 2

        return results

    def validate_gradle_file(
        self,
        config_path: Path,
        group_id: str | None = None,
        artifact_id: str | None = None,
        **kwargs: str | None,
    ) -> bool:
        """Validate a Gradle configuration path against expected G/A coordinates.

        Parameters
        ----------
        config_path : Path
            Path to a candidate Gradle configuration file.
        group_id : str | None, optional
            Expected group id. If ``None``, a fallback lookup is attempted from
            ``kwargs["group_id"]``.
        artifact_id : str | None, optional
            Expected artifact id. If ``None``, a fallback lookup is attempted from
            ``kwargs["artifact_id"]``.
        kwargs : dict[str, str | None]
            Additional keyword arguments propagated by the caller.

        Returns
        -------
        bool
            ``True`` when either validation inputs are missing (no-op validation)
            or when both expected values are present and match the extracted
            Gradle group/artifact from the project; otherwise ``False``.
        """
        group_id = group_id or kwargs.get("group_id")
        artifact_id = artifact_id or kwargs.get("artifact_id")
        repo_path = kwargs.get("repo_path")
        if group_id and artifact_id:
            repo_root = Path(repo_path) if repo_path else None
            module_root = config_path.parent
            # Validate artifact IDs against the candidate module itself so module
            # directories (for example, acra-core) can still match even when
            # settings files use dynamic include forms (e.g., include(it.name)).
            ex_group_id, ex_artifact_id, _ = extract_gav_from_gradle_project(module_root)
            if ex_group_id is None and repo_root:
                # Group is often centralized at the repository root.
                ex_group_id, _, _ = extract_gav_from_gradle_project(repo_root)
            if group_id != ex_group_id:
                return False
            return self._validate_artifact_id(module_root, artifact_id, ex_artifact_id)

        # If group or artifact ID is not provided, there is nothing to validate and return True.
        return True

    def _validate_artifact_id(
        self,
        project_path: Path,
        expected_artifact_id: str,
        extracted_artifact_id: str | None,
    ) -> bool:
        """Validate the artifact id against direct or multi-module Gradle metadata.

        Parameters
        ----------
        project_path : Path
            Path to the candidate Gradle project directory.
        expected_artifact_id : str
            Artifact id requested by detection.
        extracted_artifact_id : str | None
            Directly extracted artifact id, if present.

        Returns
        -------
        bool
            ``True`` when the expected artifact id matches either a direct
            project artifact id or a module name declared in Gradle settings.
        """
        if expected_artifact_id and expected_artifact_id == extracted_artifact_id:
            return True

        # Accept common multi-module naming where artifact ids prefix module names
        # (for example, micronaut-test-junit5 for module test-junit5).
        module_names: set[str] = {project_path.name}
        for settings_name in ("settings.gradle", "settings.gradle.kts"):
            settings_path = project_path.joinpath(settings_name)
            for module in extract_included_gradle_modules(settings_path):
                module_names.add(module.strip().strip(":").split(":")[-1])

        for module_name in module_names:
            if not module_name:
                continue
            if expected_artifact_id == module_name:
                return True
            if expected_artifact_id.endswith(f"-{module_name}"):
                return True

        return False

    def get_group_id(self, gradle_exec: str, project_path: str) -> str | None:
        """Get the group id of a Gradle project.

        A Gradle project is a directory containing a ``build.gradle`` file.
        According to the Gradle's documentation, there is a one-to-one mapping between
        a "project" and a ``build.gradle`` file.
        See: https://docs.gradle.org/current/javadoc/org/gradle/api/Project.html.

        Parameters
        ----------
        gradle_exec: str
            The absolute path to the Gradle executable.

        project_path : str
            The absolute path to the Gradle project.

        Returns
        -------
        str | None
            The group id of the project, if exists.
        """
        try:
            logger.info(
                "Identifying the group ID for the artifact. This can take a while if Gradle needs to be downloaded."
            )
            result = subprocess.run(  # nosec B603
                [gradle_exec, "properties"],
                capture_output=True,
                cwd=project_path,
                check=False,
                timeout=self.runtime_options.build_timeout,
            )
        except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as error:
            logger.debug("Could not capture the group id of the Gradle project at %s", project_path)
            logger.debug("Error: %s", error)
            return None

        if result.returncode == 0:
            lines = result.stdout.decode().split("\n")
            for line in lines:
                if line.startswith("group: "):
                    group = line.replace("group: ", "")
                    # The value of group here can be an empty string.
                    if group:
                        return group
                    break

        logger.debug("Could not capture the group id of the repo at %s", project_path)
        logger.debug("Stderr:\n%s", result.stderr)
        return None
