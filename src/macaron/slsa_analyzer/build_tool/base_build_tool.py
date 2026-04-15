# Copyright (c) 2022 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BaseBuildTool class to be inherited by other specific Build Tools."""

from __future__ import annotations

import glob
import itertools
import json
import logging
import os
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias, TypedDict

from macaron.config.defaults import defaults
from macaron.database.table_definitions import Component
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer, NoneDependencyAnalyzer
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from macaron.slsa_analyzer.checks.check_result import Confidence, Evidence, EvidenceWeightMap

if TYPE_CHECKING:
    from macaron.code_analyzer.dataflow_analysis.core import Node

logger: logging.Logger = logging.getLogger(__name__)

# Detection tuple fields:
# - config_path: relative path to the build configuration file from repo root.
# - confidence_score: confidence for this detection in [0, 1].
# - build_tool_version: detected build tool version when available.
# - parent_pom: optional path to parent configuration when applicable.
BuildToolConfig: TypeAlias = tuple[str, float, str | None, str | None]


class BuildEcosystem(str, Enum):
    """The supported build ecosystems."""

    MAVEN = "maven"
    PYPI = "pypi"
    GOLONAG = "golang"
    NPM = "npm"
    DOCKER = "docker"


class BuildToolCommand(TypedDict):
    """This class is an abstraction for build tool commands storing useful contextual data for analysis."""

    #: The parsed build tool command. This command can be any bash command whose program name is the build tool.
    command: list[str]

    #: The name of the language to build the artifact.
    language: str

    #: The list of possible language version numbers.
    language_versions: list[str] | None

    #: The list of possible language distributions.
    language_distributions: list[str] | None

    #: The URL providing information about the language distributions and versions.
    language_url: str | None

    #: The relative path to the root CI file that ultimately triggers the command.
    ci_path: str

    #: The CI step object that calls the command.
    step_node: Node | None

    #: The list of name of reachable variables that contain secrets."""
    reachable_secrets: list[str]

    #: The name of CI events that trigger the workflow running the build command.
    events: list[str] | None


def find_first_matching_file(directory: Path, pattern: str) -> Path | None:
    """
    Return the first file that matches the given glob pattern in the specified directory.

    Parameters
    ----------
    directory : Path
        Directory to search in.
    pattern : str
        Glob pattern to match.

    Returns
    -------
    Path | None
        The first matching file's path, or None if no match is found.
    """
    # Sort results to make selection deterministic across filesystems/platforms.
    for match in sorted(directory.glob(pattern), key=lambda p: p.name):
        return match
    return None


def file_exists(
    path: str,
    file_name: str,
    filters: list[str] | None = None,
    predicate: Callable[..., bool] | None = None,
    **predicate_kwargs: Any,
) -> Path | None:
    """Search recursively for the first matching file, optionally validating it with a predicate.

    The search performs a breadth-first traversal (closest directories first) and
    skips directories whose names contain any of the provided filter keywords.

    To disable filtering, pass an empty list or ``None`` to `filters`.

    Parameters
    ----------
    path : str
        Root directory to search.
    file_name : str
        File name to search for, or a glob pattern (e.g., ``"Dockerfile.*"``).
    filters : list[str] or None, optional
        Directory-name keywords to skip (case-insensitive). If ``None`` or empty,
        no directories are skipped.
    predicate : callable or None, optional
        Optional callable used to validate a matched file. If provided, a file is
        accepted only if ``predicate(candidate_path, **predicate_kwargs)``
        returns ``True``.
    predicate_kwargs : Any
        Keyword arguments forwarded to `predicate`.

    Returns
    -------
    Path | None
        The path to the first matching (and predicate-accepted) file, or ``None``
        if no match is found.
    """
    if not os.path.isdir(path):
        return None

    root_dir = Path(path)

    def _accepted(p: Path) -> bool:
        return (
            True
            if predicate is None or predicate_kwargs == {"group_id": None, "artifact_id": None}
            else bool(predicate(p, **predicate_kwargs))
        )

    # Check for file directly at root.
    if target_path := find_first_matching_file(root_dir, file_name):
        if _accepted(target_path):
            return target_path

    def _enqueue_subdirs(directory: Path, queue: deque[Path]) -> None:
        """Add non-symlink subdirectories to the search queue."""
        # Sort subdirectories so BFS traversal order is deterministic.
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            if entry.is_dir() and not entry.is_symlink():
                queue.append(entry)

    search_queue: deque[Path] = deque()
    _enqueue_subdirs(root_dir, search_queue)

    while search_queue:
        current_dir = search_queue.popleft()

        # Skip filtered directories.
        if filters and any(keyword in current_dir.name.lower() for keyword in filters):
            continue

        if candidate_path := find_first_matching_file(current_dir, file_name):
            if _accepted(candidate_path):
                return candidate_path

        _enqueue_subdirs(current_dir, search_queue)

    return None


@dataclass
class RuntimeOptions:
    """The class for build tool runtime configurations read from `defaults.ini`.

    Note that Macaron uses the options in this class to "run" a build tool.
    """

    #: The timeout used for running the build tool commands.
    build_timeout: float = 600


class BaseBuildTool(ABC):
    """This abstract class is used to implement Build Tools."""

    def __init__(self, name: str, language: BuildLanguage, purl_type: str) -> None:
        """Initialize instance.

        Parameters
        ----------
        name : str
            The name of this build tool.
        language: BuildLanguage
            The name of the language used by the programs built by the build tool.
        purl_type: str
            The type field of a PackageURL.
        """
        self.name = name
        self.language = language
        self.purl_type = purl_type
        self.entry_conf: list[str] = []
        self.build_configs: list[str] = []
        self.package_lock: list[str] = []
        self.builder: list[str] = []
        self.build_requires: list[str] = []
        self.build_backend: list[str] = []
        self.packager: list[str] = []
        self.publisher: list[str] = []
        self.interpreter: list[str] = []
        self.interpreter_flag: list[str] = []
        self.build_arg: list[str] = []
        self.deploy_arg: list[str] = []
        self.ci_build_kws: dict[str, list[str]] = {
            "github_actions": [],
            "travis_ci": [],
            "circle_ci": [],
            "gitlab_ci": [],
            "jenkins": [],
        }
        self.ci_deploy_kws: dict[str, list[str]] = {
            "github_actions": [],
            "travis_ci": [],
            "circle_ci": [],
            "gitlab_ci": [],
            "jenkins": [],
        }
        self.build_log: list[str] = []
        self.wrapper_files: list[str] = []
        self.runtime_options = RuntimeOptions()
        self.path_filters: list[str] = []
        self.build_tool_configs: list[BuildToolConfig] = []

    def __str__(self) -> str:
        return self.name

    @abstractmethod
    def is_detected(
        self,
        target: Component,
    ) -> list[BuildToolConfig]:
        """
        Return the list of build tools and their information used in the target repo.

        Parameters
        ----------
        target: Component
            The target software component.

        Returns
        -------
        list[BuildToolConfig]
            Detected build tool configurations.
        """

    def resolve_component_detection_target(
        self,
        target: Component,
    ) -> tuple[str | None, str | None, str | None]:
        """Resolve repo path and optional coordinates from a detection target.

        Parameters
        ----------
        target : Component
            Target component.

        Returns
        -------
        tuple[str | None, str | None, str | None]
            ``(repo_path, group_id, artifact_id)`` where group/artifact are
            resolved when the component PURL type matches this build tool.
        """
        repo_path = target.repository.fs_path if target.repository else None
        resolved_group_id = None
        resolved_artifact_id = None

        # The target component may have a repository-based PURL type like
        # github.com; only use name/namespace as coordinates when the type
        # matches this build tool ecosystem.
        if target.type == self.purl_type:
            resolved_group_id = target.namespace
            resolved_artifact_id = target.name

        return repo_path, resolved_group_id, resolved_artifact_id

    @abstractmethod
    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        # A list of keywords that can be used as filters while detecting build tools.
        if "builder" in defaults:
            self.path_filters = defaults.get_list("builder", "build_tool_path_filters", fallback=[])

    def match_purl_type(self, component_purl_type: str) -> bool:
        """
        Determine if the given component PURL type matches this build tool's PURL type.

        Returns ``False`` if the component PURL type matches a supported build ecosystem but does not
        match the build tool's ``purl_type``. Otherwise, returns ``True`` to allow for repositories or
        other non-standard types.

        Parameters
        ----------
        component_purl_type : str
            The PURL type of the component to check.

        Returns
        -------
        bool
            True if the type matches or is not restricted; False otherwise.
        """
        if component_purl_type.upper() in [b.name for b in BuildEcosystem] and component_purl_type != self.purl_type:
            return False
        # Otherwise return True because the component PURL type can repositories, like github.
        return True

    def get_dep_analyzer(self) -> DependencyAnalyzer:
        """Create a DependencyAnalyzer for the build tool.

        Returns
        -------
        DependencyAnalyzer
            The DependencyAnalyzer object.
        """
        return NoneDependencyAnalyzer()

    def set_build_tool_configurations(
        self, build_tool_configs: list[BuildToolConfig]
    ) -> None:
        """Set the build tool configurations for the instance.

        Parameters
        ----------
        build_tool_configs : list[BuildToolConfig]
            A list containing configuration tuples for each build tool.

        Returns
        -------
        None
        """
        self.build_tool_configs = build_tool_configs

    def get_build_dirs(self, target: Component) -> Iterable[Path]:
        """Find directories in the repository that have their own build scripts.

        This is especially important for applications that consist of multiple services.

        Parameters
        ----------
        target: Component
            The target software component.

        Yields
        ------
        Path
            The relative paths from the repo path that contain build scripts.
        """
        repo_path, _, _ = self.resolve_component_detection_target(target)
        if not repo_path:
            return

        config_paths: set[str] = set()
        for build_cfg in self.build_configs:
            config_paths.update(
                path
                for path in glob.glob(os.path.join(repo_path, "**", build_cfg), recursive=True)
                if self.is_detected(target)
            )

        list_iter = iter(sorted(config_paths, key=lambda x: (str(Path(x).parent), len(Path(x).parts))))
        try:
            cfg_path = next(list_iter)
            yield Path(cfg_path).parent.relative_to(repo_path)
            while next_item := next(list_iter):
                if next_item.startswith(str(Path(cfg_path).parent)):
                    continue
                cfg_path = next_item
                yield Path(next_item).parent.relative_to(repo_path)

        except StopIteration:
            pass

    def serialize_to_json(self, cmd: list[str]) -> str:
        """Convert a list of values to a json-encoded string so that it is easily parsable by later consumers.

        Parameters
        ----------
        cmd: list[str]
            List of command-line arguments.

        Returns
        -------
        str
            The list of command-line arguments as a json-encoded string.
        """
        return json.dumps(cmd)

    def is_build_command(self, cmd: list[str]) -> bool:
        """
        Determine if the command is a build tool command.

        Parameters
        ----------
        cmd: list[str]
            List of command-line arguments.

        Returns
        -------
        bool
            True if the command is a build tool command.
        """
        # Check for empty or invalid commands.
        if not cmd or not cmd[0]:
            return False
        # The first argument in a bash command is the program name.
        # So first check that the program name is a supported build tool name.
        # We need to handle cases where the first argument is a path to the program.
        cmd_program_name = os.path.basename(cmd[0])
        if not cmd_program_name:
            logger.debug("Found invalid program name %s.", cmd[0])
            return False

        build_tools = set(itertools.chain(self.builder, self.packager, self.publisher, self.interpreter))
        if any(tool for tool in build_tools if tool == cmd_program_name):
            return True

        return False

    def match_cmd_args(self, cmd: list[str], tools: list[str], args: list[str]) -> bool:
        """
        Check if the build command matches any of the tools and the command-line arguments.

        If build command's first element, which is the program name matches any of the `tools` names and any of its arguments
        match any of the arguments in `args`, this function returns True.

        Parameters
        ----------
        cmd: list[str]
            The command-line arguments.
        tools: list[str]
            The name of tools that will be matched with the program name in the bash command.
        args: list[str]
            The lit of arguments that should match with the bash command.

        Returns
        -------
        bool
            True if the provided command matches the tool and arguments.
        """
        cmd_program_name = os.path.basename(cmd[0])

        if cmd_program_name in tools:
            # Check the arguments in the bash command.
            # If there are no args expected for this build tool, accept the command.
            if not args:
                logger.debug("No build arguments required. Accept the %s command.", self.serialize_to_json(cmd))
                return True

            for word in cmd[1:]:
                # TODO: allow plugin versions in arguments, e.g., maven-plugin:1.6.8:deploy.
                if word in args:
                    logger.debug("Found the command %s.", self.serialize_to_json(cmd))
                    return True

        return False

    def infer_confidence_deploy_workflow(self, ci_path: str, provenance_workflow: str | None = None) -> Confidence:
        """
        Infer the confidence level for the deploy CI workflow.

        Parameters
        ----------
        ci_path: str
            The path to the CI workflow.
        provenance_workflow: str | None
            The relative path to the root CI file that is captured in a provenance or None if provenance is not found.

        Returns
        -------
        Confidence
            The confidence level for the deploy command.
        """
        # Apply heuristics and assign weights and scores for the discovered evidence.
        evidence_weight_map = EvidenceWeightMap(
            [
                Evidence(name="ci_workflow_deploy", found=False, weight=2),
            ]
        )

        # Check if the CI workflow path for the build command is captured in a provenance file.
        if provenance_workflow and ci_path.endswith(provenance_workflow):
            # We add this evidence only if a provenance is found to make sure we pick the right triggering
            # workflow in the call graph. Otherwise, lack of provenance would have always lowered the
            # confidence score, making the rest of the heuristics less effective.
            evidence_weight_map.add(
                Evidence(name="workflow_in_provenance", found=True, weight=5),
            )

        # Check workflow names.
        deploy_keywords = ["release", "deploy", "publish"]
        test_keywords = ["test", "snapshot"]
        for deploy_kw in deploy_keywords:
            if deploy_kw in os.path.basename(ci_path.lower()):
                is_test = (test_kw for test_kw in test_keywords if test_kw in os.path.basename(ci_path.lower()))
                if any(is_test):
                    continue
                evidence_weight_map.update_result(name="ci_workflow_release", found=True)
                break

        return Confidence.normalize(evidence_weight_map=evidence_weight_map)

    def infer_confidence_deploy_command(
        self, cmd: BuildToolCommand, provenance_workflow: str | None = None
    ) -> Confidence:
        """
        Infer the confidence level for the deploy command.

        Parameters
        ----------
        cmd: BuildToolCommand
            The build tool command object.
        provenance_workflow: str | None
            The relative path to the root CI file that is captured in a provenance or None if provenance is not found.

        Returns
        -------
        Confidence
            The confidence level for the deploy command.
        """
        # Apply heuristics and assign weights and scores for the discovered evidence.
        # TODO: infer the scores based on existing data using probabilistic inference.
        # Initialize the map.
        evidence_weight_map = EvidenceWeightMap(
            [
                Evidence(name="reachable_secrets", found=False, weight=1),
                Evidence(name="ci_workflow_name", found=False, weight=2),
                Evidence(name="release_event", found=False, weight=2),
            ]
        )

        # Check if the CI workflow path for the build command is captured in a provenance file.
        if provenance_workflow and cmd["ci_path"].endswith(provenance_workflow):
            # We add this evidence only if a provenance is found to make sure we pick the right triggering
            # workflow in the call graph. Otherwise, lack of provenance would have always lowered the
            # confidence score, making the rest of the heuristics less effective.
            evidence_weight_map.add(
                Evidence(name="workflow_in_provenance", found=True, weight=5),
            )

        # Check if secrets are present in the caller job.
        if cmd["reachable_secrets"]:
            evidence_weight_map.update_result(name="reachable_secrets", found=True)

        # Check workflow names.
        deploy_keywords = ["release", "deploy", "publish"]
        for kw in deploy_keywords:
            if kw in os.path.basename(cmd["ci_path"]).lower():
                evidence_weight_map.update_result(name="ci_workflow_name", found=True)
                break

        # Check if the CI workflow is triggered by a release event.
        if cmd["events"] and "release" in cmd["events"]:
            evidence_weight_map.update_result(name="release_event", found=True)

        return Confidence.normalize(evidence_weight_map=evidence_weight_map)

    def is_deploy_command(
        self, cmd: BuildToolCommand, excluded_configs: list[str] | None = None, provenance_workflow: str | None = None
    ) -> tuple[bool, Confidence]:
        """
        Determine if the command is a deploy command.

        A deploy command usually performs multiple tasks, such as compilation, packaging, and publishing the artifact.
        This function filters the build tool commands that are called from the configuration files provided as input.

        Parameters
        ----------
        cmd: BuildToolCommand
            The build tool command object.
        excluded_configs: list[str] | None
            Build tool commands that are called from these configuration files are excluded.
        provenance_workflow: str | None
            The relative path to the root CI file that is captured in a provenance or None if provenance is not found.

        Returns
        -------
        tuple[bool, Confidence]
            Return True along with the inferred confidence level if the command is a deploy tool command.
        """
        # Check the language.
        if cmd["language"] is not self.language:
            return False, Confidence.HIGH
        # Some projects use a publisher tool and some use the build tool with deploy arguments.
        deploy_tool = self.publisher if self.publisher else self.builder

        if not self.match_cmd_args(cmd=cmd["command"], tools=deploy_tool, args=self.deploy_arg):
            return False, Confidence.HIGH

        # Check if the CI workflow is a configuration for a known tool.
        if excluded_configs and os.path.basename(cmd["ci_path"]) in excluded_configs:
            return False, Confidence.HIGH

        return True, self.infer_confidence_deploy_command(cmd=cmd, provenance_workflow=provenance_workflow)

    def is_package_command(
        self, cmd: BuildToolCommand, excluded_configs: list[str] | None = None
    ) -> tuple[bool, Confidence]:
        """
        Determine if the command is a packaging command.

        A packaging command usually performs multiple tasks, such as compilation and creating the artifact.
        This function filters the build tool commands that are called from the configuration files provided as input.

        Parameters
        ----------
        cmd: BuildToolCommand
            The build tool command object.
        excluded_configs: list[str] | None
            Build tool commands that are called from these configuration files are excluded.

        Returns
        -------
        tuple[bool, Confidence]
            Return True along with the inferred confidence level if the command is a build tool command.
        """
        # Check the language.
        if cmd["language"] is not self.language:
            return False, Confidence.HIGH

        builder = self.packager if self.packager else self.builder

        if not self.match_cmd_args(cmd=cmd["command"], tools=builder, args=self.build_arg):
            return False, Confidence.HIGH

        # Check if the CI workflow is a configuration for a known tool.
        if excluded_configs and os.path.basename(cmd["ci_path"]) in excluded_configs:
            return False, Confidence.HIGH

        return True, Confidence.HIGH
