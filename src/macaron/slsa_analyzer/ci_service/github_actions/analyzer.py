# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides the intermediate representations and analysis functions for GitHub Actions."""

import logging
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeGuard, cast

from macaron.code_analyzer.call_graph import BaseNode
from macaron.config.global_config import global_config
from macaron.errors import CallGraphError, GitHubActionsValueError, ParseError
from macaron.parsers.actionparser import get_step_input
from macaron.parsers.actionparser import parse as parse_action
from macaron.parsers.bashparser import BashNode, BashScriptType, create_bash_node
from macaron.parsers.github_workflow_model import (
    ActionStep,
    Identified,
    Job,
    NormalJob,
    ReusableWorkflowCallJob,
    Step,
    Workflow,
    is_action_step,
    is_normal_job,
    is_reusable_workflow_call_job,
)
from macaron.slsa_analyzer.build_tool.language import BuildLanguage, Language

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThirdPartyAction:
    """The representation for a third-party GitHub Action."""

    #: The name of the GitHub Action.
    action_name: str

    #: The version of the GitHub Action.
    action_version: str | None


class GitHubWorkflowType(str, Enum):
    """This class represents different GitHub Actions workflow types."""

    INTERNAL = "internal"  # Workflows declared in the repo.
    EXTERNAL = "external"  # Third-party workflows.
    REUSABLE = "reusable"  # Reusable workflows.


class GitHubWorkflowNode(BaseNode):
    """This class represents a callgraph node for GitHub Actions workflows."""

    def __init__(
        self,
        name: str,
        node_type: GitHubWorkflowType,
        source_path: str,
        parsed_obj: Workflow | Identified[ReusableWorkflowCallJob] | ActionStep,
        model: ThirdPartyAction | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize instance.

        Parameters
        ----------
        name : str
            Name of the workflow (or URL for reusable and external workflows).
        node_type : GitHubWorkflowType
            The type of workflow.
        source_path : str
            The path of the workflow.
        parsed_obj : Workflow | Identified[ReusableWorkflowCallJob] | ActionStep
            The parsed Actions workflow object. Actual type must correspond to node type.
            (INTERNAL -> Workflow, REUSABLE -> Identified[ReusableWorkflowCallJob], EXTERNAL -> ActionStep)
        caller: BaseNode | None
            The caller node.
        model: ThirdPartyAction | None
            The static analysis abstraction for the third-party GitHub Action.
        """
        super().__init__(**kwargs)
        self.name = name
        self.node_type: GitHubWorkflowType = node_type
        self.source_path = source_path
        self.parsed_obj = parsed_obj
        self.model = model

    def __str__(self) -> str:
        return f"GitHubWorkflowNode({self.name},{self.node_type})"


class GitHubJobNode(BaseNode):
    """This class represents a callgraph node for GitHub Actions jobs."""

    def __init__(self, name: str, source_path: str, parsed_obj: Identified[Job], **kwargs: Any) -> None:
        """Initialize instance.

        Parameters
        ----------
        name : str
            Name of the workflow (or URL for reusable and external workflows).
        source_path : str
            The path of the workflow.
        parsed_obj : Identified[Job]
            The parsed Actions workflow object.
        caller: BaseNode
            The caller node.
        """
        super().__init__(**kwargs)
        self.name = name
        self.source_path = source_path
        self.parsed_obj = parsed_obj

    def __str__(self) -> str:
        return f"GitHubJobNode({self.name})"


def is_parsed_obj_workflow(
    parsed_obj: Workflow | Identified[ReusableWorkflowCallJob] | ActionStep,
) -> TypeGuard[Workflow]:
    """Type guard for Workflow parsed_obj."""
    return not isinstance(parsed_obj, Identified) and "jobs" in parsed_obj


def is_parsed_obj_reusable_workflow_call_job(
    obj: Workflow | Identified[ReusableWorkflowCallJob] | ActionStep,
) -> TypeGuard[Identified[ReusableWorkflowCallJob]]:
    """Type guard for ReusableWorkflowCallJob parsed_obj."""
    return isinstance(obj, Identified)


def is_parsed_obj_action_step(
    parsed_obj: Workflow | Identified[ReusableWorkflowCallJob] | ActionStep,
) -> TypeGuard[ActionStep]:
    """Type guard for ActionStep parsed_obj."""
    return not isinstance(parsed_obj, Identified) and "uses" in parsed_obj


def find_expression_variables(value: str, exp_var: str) -> Iterable[str]:
    """Find all the matching GitHub Actions expression variables in a string value.

    GitHub Actions Expression syntax: ${{ <expression> }}
    See https://docs.github.com/en/actions/learn-github-actions/expressions#about-expressions

    Parameters
    ----------
    value: str
        The value in which the expression values are searched.
    exp_var: str
        The expression variable name.

    Yields
    ------
    Iterable[str]
        The expression variable names.

    Examples
    --------
    >>> list(find_expression_variables("echo ${{ inputs.foo }}", "inputs"))
    ['foo']
    >>> list(find_expression_variables("echo ${{ inputs.foo }} ${{ inputs.bar }}", "inputs"))
    ['foo', 'bar']
    >>> list(find_expression_variables("echo ${{ inputs.foo }} ${{ inputs.bar }}", "matric"))
    []
    """
    expressions = re.findall(r"\$\{\{.*?\}\}", value)
    pattern = r"\$\{\{\s+" + exp_var + r"\.(?P<variable>(.*?))\s+\}\}"
    for exp in expressions:
        match = re.match(pattern, exp)
        if match:
            yield match.group("variable")


def resolve_matrix_variable(job_node: GitHubJobNode, var: str) -> Iterable[str]:
    """Resolve the value of a GitHub Actions matrix variable.

    For the specification of matrix variables in GitHub Actions see:
    https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs

    Parameters
    ----------
    job_node: GitHubJobNode
        The target GitHub Actions job.
    var: str
        The matrix variable that needs to be resolved.

    Yields
    ------
    str
        The possible values of the matrix variable.

    Raises
    ------
    GitHubActionsValueError
        When the matrix variable cannot be found.
    """
    job_obj = job_node.parsed_obj.obj
    if "strategy" not in job_obj:
        raise GitHubActionsValueError(f"Unable to find `strategy` in {job_node.source_path} GitHub Action.")
    if "matrix" not in job_obj["strategy"]:
        raise GitHubActionsValueError(f"Unable to find `matrix` in {job_node.source_path} GitHub Action.")
    matrix = job_obj["strategy"]["matrix"]
    if not isinstance(matrix, dict):
        raise GitHubActionsValueError(f"Unable to resolve matrix in {job_node.source_path} GitHub Action.")

    matrix_vals = matrix.get(var)
    if matrix_vals is None:
        raise GitHubActionsValueError(f"Unable to find variable {var} in {job_node.source_path} GitHub Action.")

    if isinstance(matrix_vals, list):
        for val in matrix_vals:
            # TODO: type of val permits dict/list, how to handle it? Just return Configuration instead of str
            # and let the caller handle it?
            if isinstance(val, str):
                yield val
            if isinstance(val, int):
                yield str(val)
            if isinstance(val, float):
                yield str(val)
            if isinstance(val, bool):
                yield "true" if val else "false"
    else:
        raise GitHubActionsValueError(f"Unable to resolve matrix in {job_node.source_path} GitHub Action.")


def is_expression(value: str) -> bool:
    """Determine if a value is a GitHub Actions expression.

    Parameters
    ----------
    value: str
        The input value.

    Returns
    -------
    bool
        True if the input value is a GitHub Actions expression.

    Examples
    --------
    >>> is_expression("${{ foo }}")
    True
    >>> is_expression("${{ foo }")
    False
    >>> is_expression("${ foo }")
    False
    """
    return re.match(r"\$\{\{.*?\}\}", value) is not None


def find_language_setup_action(job_node: GitHubJobNode, lang_name: BuildLanguage) -> Language | None:
    """Find the step that calls a language setup GitHub Actions and return the model.

    Parameters
    ----------
    job_node: GitHubJobNode
        The target GitHub Actions job node.
    lang_name: BuildLanguage
        The target language used in the build.

    Returns
    -------
    Language | None
        The language model for the language setup GitHub Action or None.
    """
    for callee in job_node.callee:
        model = callee.model
        # Check if the model implements the Language protocol.
        if isinstance(model, Language):
            if model.lang_name == lang_name:
                return model
    return None


def build_call_graph_from_node(node: GitHubWorkflowNode, repo_path: str) -> None:
    """Analyze the GitHub Actions node to build the call graph.

    Parameters
    ----------
    node : GitHubWorkflowNode
        The node for a single GitHub Actions workflow.
    repo_path: str
        The file system path to the repo.
    """
    if not is_parsed_obj_workflow(node.parsed_obj):
        return
    jobs = node.parsed_obj["jobs"]
    for job_name, job in jobs.items():
        job_with_id = Identified[Job](job_name, job)
        job_node = GitHubJobNode(name=job_name, source_path=node.source_path, parsed_obj=job_with_id, caller=node)
        node.add_callee(job_node)

        if is_normal_job(job):
            # Add third-party workflows.
            steps = job.get("steps")
            if steps is None:
                continue
            for step in steps:
                if is_action_step(step):
                    # TODO: change source_path for external workflows.
                    action_name = step["uses"]
                    external_node = GitHubWorkflowNode(
                        name=action_name,
                        node_type=GitHubWorkflowType.EXTERNAL,
                        source_path="",
                        parsed_obj=step,
                        caller=job_node,
                    )
                    external_node.model = create_third_party_action_model(external_node)
                    job_node.add_callee(external_node)

                # Check the shell type configuration. We currently can support `bash`` and `sh`.
                # By default `bash`` is used on non-Windows runners, which we support.
                # See https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#defaultsrunshell
                # TODO: support Powershell for Windows runners, which is the default shell in GitHub Actions.
                # Right now, the script with the default shell is passed to the parser, which will fail
                # if the runner is Windows and Powershell is used. But there is no easy way to avoid passing
                # the script because that means we need to accurately determine the runner's OS.
                elif step.get("run") and ("shell" not in step or step["shell"] in {"bash", "sh"}):
                    try:
                        name = "UNKNOWN"
                        node_id = None
                        if "id" in step:
                            node_id = step["id"]
                        if "name" in step:
                            name = step["name"]

                        callee = create_bash_node(
                            name=name,
                            node_id=node_id,
                            node_type=BashScriptType.INLINE,
                            source_path=node.source_path,
                            ci_step_ast=step,
                            repo_path=repo_path,
                            caller=job_node,
                            recursion_depth=0,
                        )
                    except CallGraphError as error:
                        logger.debug(error)
                        continue
                    job_node.add_callee(callee)

        elif is_reusable_workflow_call_job(job):
            workflow_call_job_with_id = Identified[ReusableWorkflowCallJob](job_name, job)
            # Add reusable workflows.
            logger.debug("Found reusable workflow: %s.", job["uses"])
            # TODO: change source_path for reusable workflows.
            reusable_node = GitHubWorkflowNode(
                name=job["uses"],
                node_type=GitHubWorkflowType.REUSABLE,
                source_path="",
                parsed_obj=workflow_call_job_with_id,
                caller=job_node,
            )
            reusable_node.model = create_third_party_action_model(reusable_node)
            job_node.add_callee(reusable_node)


def build_call_graph_from_path(root: BaseNode, workflow_path: str, repo_path: str, macaron_path: str = "") -> BaseNode:
    """Build the call Graph for GitHub Actions workflows.

    At the moment it does not analyze third-party workflows to include their callees.

    Parameters
    ----------
    root : BaseNode
        The root call graph node.
    workflow_path: str
        The path to the CI workflow file.
    repo_path: str
        The path to the target repository.
    macaron_path: str
        Macaron's root path (optional).

    Returns
    -------
    BaseNode
        The callgraph node for the GitHub Actions workflow.

    Raises
    ------
    ParseError
        When parsing the workflow fails with error.
    """
    if not macaron_path:
        macaron_path = global_config.macaron_path

    # Parse GitHub Actions workflows.
    logger.debug(
        "Parsing %s",
        workflow_path,
    )
    try:
        parsed_obj: Workflow = parse_action(workflow_path)
    except ParseError as error:
        logger.error("Unable to parse GitHub Actions at the target %s: %s", repo_path, error)
        raise ParseError from error

    # Add internal workflows.
    workflow_name = os.path.basename(workflow_path)
    workflow_node = GitHubWorkflowNode(
        name=workflow_name,
        node_type=GitHubWorkflowType.INTERNAL,
        source_path=workflow_path,
        parsed_obj=parsed_obj,
        caller=root,
    )
    build_call_graph_from_node(workflow_node, repo_path=repo_path)

    return workflow_node


def get_reachable_secrets(step_node: BashNode) -> Iterable[str]:
    """Get reachable secrets to a GitHub Actions step.

    Parameters
    ----------
    step_node: BashNode
        The target GitHub Action step node.

    Yields
    ------
    str
        The reachable secret variable name.
    """
    job_node = step_node.caller
    if not isinstance(job_node, GitHubJobNode):
        return

    def _find_secret_keys(ast: NormalJob | ReusableWorkflowCallJob | Step | None) -> Iterable[str]:
        if ast is None:
            return
        if "uses" in ast:
            return
        normal_job = cast(NormalJob, ast)
        if "env" in normal_job:
            env = normal_job["env"]
            if isinstance(env, dict):
                for key, val in env.items():
                    if isinstance(val, str):
                        if list(find_expression_variables(value=val, exp_var="secrets")):
                            yield key

    # Get reachable secrets set as environment variables in the job.
    yield from _find_secret_keys(job_node.parsed_obj.obj)

    # Get reachable secrets set as environment variables in the step.
    if step_node.node_type == BashScriptType.INLINE:
        yield from _find_secret_keys(step_node.parsed_step_obj)


def get_ci_events(workflow_node: GitHubWorkflowNode) -> list[str] | None:
    """Get the CI events that trigger the GitHub Action workflow.

    Parameters
    ----------
    workflow_node: GitHubWorkflowNode
        The target GitHub Action workflow node.

    Returns
    -------
    list[str] | None
        The list of event names or None.
    """
    result: list[str] = []
    ast = workflow_node.parsed_obj
    if not isinstance(ast, dict) or "on" not in ast:
        raise GitHubActionsValueError(f"Unable to find `on` event in {workflow_node.source_path} GitHub Action.")

    on = cast(Workflow, ast)["on"]

    if isinstance(on, str):
        result.append(on)
    elif isinstance(on, list):
        for hook in on:
            result.append(hook)
    else:
        for key in on:
            result.append(key)

    return result


class SetupJava(Language, ThirdPartyAction):
    """This class models the official setup-java GitHub Action from GitHub.

    For the table of supported distributions see:
    https://github.com/actions/setup-java?tab=readme-ov-file#supported-distributions
    """

    #: Name of the GitHub Action.
    action_name = "actions/setup-java"

    #: Version of the GitHub Action.
    action_version: None

    def __init__(self, external_node: GitHubWorkflowNode):
        """Initialize the setup-java GitHub Action model.

        Parameters
        ----------
        external_node: GitHubWorkflowNode
            The external GitHub Action workflow node.
        """
        # external_node is assumed to be an EXTERNAL node with ActionStep parsed_obj.
        step = external_node.parsed_obj
        if not is_parsed_obj_action_step(step):
            raise ValueError("Expected an action step node")
        self._lang_name = BuildLanguage.JAVA
        self._lang_distributions = None
        self._lang_versions = None
        self._lang_url = "https://github.com/actions/setup-java"
        lang_distribution_exp = None
        lang_version_exp = None
        if distribution := get_step_input(step, key="distribution"):
            if not is_expression(distribution):
                self._lang_distributions = [distribution]
            else:
                lang_distribution_exp = distribution
        if java_version := get_step_input(step, key="java-version"):
            if not is_expression(java_version):
                self._lang_versions = [java_version]
            else:
                lang_version_exp = java_version
        # Handle matrix values.
        matrix_values = {}
        if lang_distribution_exp and "matrix." in lang_distribution_exp:
            matrix_values["lang_distribution_var"] = find_expression_variables(
                value=lang_distribution_exp, exp_var="matrix"
            )
        if lang_version_exp and "matrix." in lang_version_exp:
            matrix_values["lang_version_var"] = find_expression_variables(value=lang_version_exp, exp_var="matrix")

        if matrix_values:
            job_node = external_node.caller
            if job_node is None:
                logger.debug("Unable to find the caller GitHub Action job for step %s.", external_node.name)
                return
            try:
                if (variables := matrix_values.get("lang_distribution_var")) is not None:
                    values: list[str] = []
                    for var in variables:
                        values.extend(resolve_matrix_variable(job_node, var))
                    if values:
                        self._lang_distributions = values
            except GitHubActionsValueError as error:
                logger.debug(error)

            try:
                if (variables := matrix_values.get("lang_version_var")) is not None:
                    values = []
                    for var in variables:
                        values.extend(resolve_matrix_variable(job_node, var))
                    if values:
                        self._lang_versions = values
            except GitHubActionsValueError as error:
                logger.debug(error)

    @property
    def lang_name(self) -> str:
        """Get the name of the language."""
        return self._lang_name

    @property
    def lang_versions(self) -> list[str] | None:
        """Get the possible version of the language."""
        return self._lang_versions

    @property
    def lang_distributions(self) -> list[str] | None:
        """Get the possible distributions of the language."""
        return self._lang_distributions

    @property
    def lang_url(self) -> str | None:
        """Get the URL that provides information about the language distributions and versions."""
        return self._lang_url


class OracleSetupJava(Language, ThirdPartyAction):
    """This class models the Oracle setup-java GitHub Action.

    For the table of supported distributions see:
    # https://github.com/oracle-actions/setup-java?tab=readme-ov-file#input-overview
    """

    #: Name of the GitHub Action.
    action_name = "oracle-actions/setup-java"

    #: Version of the GitHub Action.
    action_version: None

    def __init__(self, external_node: GitHubWorkflowNode):
        """Initialize the Oracle setup-java GitHub Action model.

        Parameters
        ----------
        external_node: GitHubWorkflowNode
            The external GitHub Action workflow node.
        """
        # external_node is assumed to be an EXTERNAL node with ActionStep parsed_obj.
        step = external_node.parsed_obj
        if not is_parsed_obj_action_step(step):
            raise ValueError("Expected an action step node")
        self._lang_name = BuildLanguage.JAVA
        self._lang_distributions = None
        self._lang_versions = None
        self._lang_url = "https://github.com/oracle-actions/setup-java"
        lang_distribution_exp = None
        lang_version_exp = None
        if website := get_step_input(step, key="website"):
            if not is_expression(website):
                self._lang_distributions = [website]
            else:
                lang_distribution_exp = website
        if java_release := get_step_input(step, key="release"):
            if not is_expression(java_release):
                self._lang_versions = [java_release]
            else:
                lang_version_exp = java_release
        # Handle matrix values.
        matrix_values = {}
        if lang_distribution_exp and "matrix." in lang_distribution_exp:
            matrix_values["lang_distribution_var"] = find_expression_variables(
                value=lang_distribution_exp, exp_var="matrix"
            )
        if lang_version_exp and "matrix." in lang_version_exp:
            matrix_values["lang_version_var"] = find_expression_variables(value=lang_version_exp, exp_var="matrix")

        if matrix_values:
            job_node = external_node.caller
            if job_node is None:
                logger.debug("Unable to find the caller GitHub Action job for step %s.", external_node.name)
                return
            try:
                if (variables := matrix_values.get("lang_distribution_var")) is not None:
                    values: list[str] = []
                    for var in variables:
                        values.extend(resolve_matrix_variable(job_node, var))
                    if values:
                        self._lang_distributions = values
            except GitHubActionsValueError as error:
                logger.debug(error)

            try:
                if (variables := matrix_values.get("lang_version_var")) is not None:
                    values = []
                    for var in variables:
                        values.extend(resolve_matrix_variable(job_node, var))
                    if values:
                        self._lang_versions = values
            except GitHubActionsValueError as error:
                logger.debug(error)

    @property
    def lang_name(self) -> str:
        """Get the name of the language."""
        return self._lang_name

    @property
    def lang_versions(self) -> list[str] | None:
        """Get the possible version of the language."""
        return self._lang_versions

    @property
    def lang_distributions(self) -> list[str] | None:
        """Get the possible distributions of the language."""
        return self._lang_distributions

    @property
    def lang_url(self) -> str | None:
        """Get the URL that provides information about the language distributions and versions."""
        return self._lang_url


class GraalVMSetup(Language, ThirdPartyAction):
    """This class models the GraalVM setup GitHub Action from GitHub.

    For the table of supported distributions see:
    https://github.com/graalvm/setup-graalvm
    """

    #: Name of the GitHub Action.
    action_name = "graalvm/setup-graalvm"

    #: Version of the GitHub Action.
    action_version: None

    def __init__(self, external_node: GitHubWorkflowNode):
        """Initialize the setup-java GitHub Action model.

        Parameters
        ----------
        external_node: GitHubWorkflowNode
            The external GitHub Action workflow node.
        """
        # external_node is assumed to be an EXTERNAL node with ActionStep parsed_obj.
        step = external_node.parsed_obj
        if not is_parsed_obj_action_step(step):
            raise ValueError("Expected an action step node")
        self._lang_name = BuildLanguage.JAVA
        self._lang_distributions = None
        self._lang_versions = None
        self._lang_url = "https://github.com/graalvm/setup-graalvm"
        lang_distribution_exp = None
        lang_version_exp = None
        if distribution := get_step_input(step, key="distribution"):
            if not is_expression(distribution):
                self._lang_distributions = [distribution]
            else:
                lang_distribution_exp = distribution
        if java_version := get_step_input(step, key="java-version"):
            if not is_expression(java_version):
                self._lang_versions = [java_version]
            else:
                lang_version_exp = java_version
        # Handle matrix values.
        matrix_values = {}
        if lang_distribution_exp and "matrix." in lang_distribution_exp:
            matrix_values["lang_distribution_var"] = find_expression_variables(
                value=lang_distribution_exp, exp_var="matrix"
            )
        if lang_version_exp and "matrix." in lang_version_exp:
            matrix_values["lang_version_var"] = find_expression_variables(value=lang_version_exp, exp_var="matrix")

        if matrix_values:
            job_node = external_node.caller
            if job_node is None:
                logger.debug("Unable to find the caller GitHub Action job for step %s.", external_node.name)
                return
            try:
                if (variables := matrix_values.get("lang_distribution_var")) is not None:
                    values: list[str] = []
                    for var in variables:
                        values.extend(resolve_matrix_variable(job_node, var))
                    if values:
                        self._lang_distributions = values
            except GitHubActionsValueError as error:
                logger.debug(error)

            try:
                if (variables := matrix_values.get("lang_version_var")) is not None:
                    values = []
                    for var in variables:
                        values.extend(resolve_matrix_variable(job_node, var))
                    if values:
                        self._lang_versions = values
            except GitHubActionsValueError as error:
                logger.debug(error)

    @property
    def lang_name(self) -> str:
        """Get the name of the language."""
        return self._lang_name

    @property
    def lang_versions(self) -> list[str] | None:
        """Get the possible version of the language."""
        return self._lang_versions

    @property
    def lang_distributions(self) -> list[str] | None:
        """Get the possible distributions of the language."""
        return self._lang_distributions

    @property
    def lang_url(self) -> str | None:
        """Get the URL that provides information about the language distributions and versions."""
        return self._lang_url


def create_third_party_action_model(external_node: GitHubWorkflowNode) -> ThirdPartyAction:
    """Create an instances of third-party model object.

    Parameters
    ----------
    external_node: GitHubWorkflowNode
        The external GitHub Actions workflow node.

    Returns
    -------
    ThirdPartyAction
        An instance object for the ThirdPartyAction model.
    """
    action_name = external_node.name
    action_version = None
    if "@" in external_node.name:
        action_name, action_version = external_node.name.split("@", maxsplit=1)
    match action_name:
        case "actions/setup-java":
            return SetupJava(external_node=external_node)
        case "oracle-actions/setup-java":
            return OracleSetupJava(external_node=external_node)
        case "graalvm/setup-graalvm":
            return GraalVMSetup(external_node=external_node)
    return ThirdPartyAction(action_name=action_name, action_version=action_version)
