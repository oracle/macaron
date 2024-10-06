# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BaseBuildTool class to be inherited by other specific Build Tools."""

import glob
import itertools
import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from macaron.code_analyzer.call_graph import BaseNode
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer
from macaron.slsa_analyzer.build_tool.language import BuildLanguage
from macaron.slsa_analyzer.checks.check_result import Confidence, Evidence, EvidenceWeightMap

logger: logging.Logger = logging.getLogger(__name__)


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
    step_node: BaseNode

    #: The list of name of reachable variables that contain secrets."""
    reachable_secrets: list[str]

    #: The name of CI events that trigger the workflow running the build command.
    events: list[str] | None


def file_exists(path: str, file_name: str) -> bool:
    """Return True if a file exists in a directory.

    This method searches in the directory recursively.

    Parameters
    ----------
    path : str
        The path to search for the file.
    file_name : str
        The name of the file to search.

    Returns
    -------
    bool
        True if file_name exists else False.
    """
    pattern = os.path.join(path, "**", file_name)
    files_detected = glob.iglob(pattern, recursive=True)
    try:
        next(files_detected)
        return True
    except StopIteration:
        return False


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

    def __str__(self) -> str:
        return self.name

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""

    @abstractmethod
    def get_dep_analyzer(self) -> DependencyAnalyzer:
        """Create a DependencyAnalyzer for the build tool.

        Returns
        -------
        DependencyAnalyzer
            The DependencyAnalyzer object.
        """

    def get_build_dirs(self, repo_path: str) -> Iterable[Path]:
        """Find directories in the repository that have their own build scripts.

        This is especially important for applications that consist of multiple services.

        Parameters
        ----------
        repo_path: str
            The path to the target repo.

        Yields
        ------
        Path
            The relative paths from the repo path that contain build scripts.
        """
        config_paths: set[str] = set()
        for build_cfg in self.build_configs:
            config_paths.update(
                path
                for path in glob.glob(os.path.join(repo_path, "**", build_cfg), recursive=True)
                if self.is_detected(str(Path(path).parent))
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
