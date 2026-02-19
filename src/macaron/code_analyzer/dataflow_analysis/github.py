# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Dataflow analysis implementation for analysing GitHub Actions Workflow build pipelines."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from graphlib import TopologicalSorter

from macaron.code_analyzer.dataflow_analysis import bash, core, evaluation, facts, github_expr, models, printing
from macaron.errors import CallGraphError
from macaron.parsers import github_workflow_model


@dataclass(frozen=True)
class GitHubActionsWorkflowContext(core.Context):
    """Context for the top-level scope of a GitHub Actions Workflow."""

    #: Outer analysis context.
    analysis_context: core.ContextRef[core.AnalysisContext]
    #: Scope for artifact storage within the pipeline execution (for upload/download artifact).
    artifacts: core.ContextRef[facts.Scope]
    #: Scope for artifacts published as GitHub releases by the pipeline.
    releases: core.ContextRef[facts.Scope]
    #: Scope for environment variables (env block at top-level of workflow).
    env: core.ContextRef[facts.Scope]
    #: Scope for variables within the workflow.
    workflow_variables: core.ContextRef[facts.Scope]
    #: Scope for console output.
    console: core.ContextRef[facts.Scope]
    #: Filepath of workflow file.
    source_filepath: str

    @staticmethod
    def create(
        analysis_context: core.ContextRef[core.AnalysisContext], source_filepath: str
    ) -> GitHubActionsWorkflowContext:
        """Create a new workflow context and its associated scopes.

        Parameters
        ----------
        analysis_context: core.ContextRef[core.AnalysisContext]
            Outer analysis context.
        source_filepath: str
            Filepath of workflow file.

        Returns
        -------
        GitHubActionsWorkflowContext
            The new workflow context.
        """
        return GitHubActionsWorkflowContext(
            analysis_context=analysis_context.get_non_owned(),
            artifacts=core.OwningContextRef(facts.Scope("artifacts")),
            releases=core.OwningContextRef(facts.Scope("releases")),
            env=core.OwningContextRef(facts.Scope("env")),
            workflow_variables=core.OwningContextRef(facts.Scope("workflow_vars")),
            console=core.OwningContextRef(facts.Scope("console")),
            source_filepath=source_filepath,
        )

    def direct_refs(self) -> Iterator[core.ContextRef[core.Context] | core.ContextRef[facts.Scope]]:
        """Yield the direct references of the context, either to scopes or to other contexts."""
        yield self.analysis_context
        yield self.artifacts
        yield self.releases
        yield self.env
        yield self.workflow_variables
        yield self.console


@dataclass(frozen=True)
class GitHubActionsJobContext(core.Context):
    """Context for a job within a GitHub Actions Workflow."""

    #: Outer workflow context.
    workflow_context: core.ContextRef[GitHubActionsWorkflowContext]
    #: Scope for filesystem used by the job and its steps.
    filesystem: core.ContextRef[facts.Scope]
    #: Scope for environment variables (env block at job level).
    env: core.ContextRef[facts.Scope]
    #: Scope for variables within the job (step output variables, etc.).
    job_variables: core.ContextRef[facts.Scope]

    @staticmethod
    def create(workflow_context: core.ContextRef[GitHubActionsWorkflowContext]) -> GitHubActionsJobContext:
        """Create a new job context and its associated scopes.

        Env and job variables scopes inherit from outer context.

        Parameters
        ----------
        workflow_context: core.ContextRef[GitHubActionsWorkflowContext]
            Outer workflow context.

        Returns
        -------
        GitHubActionsJobContext
            The new job context.
        """
        return GitHubActionsJobContext(
            workflow_context=workflow_context.get_non_owned(),
            filesystem=core.OwningContextRef(facts.Scope("filesystem")),
            env=core.OwningContextRef(facts.Scope("env", workflow_context.ref.env.ref)),
            job_variables=core.OwningContextRef(facts.Scope("job_vars", workflow_context.ref.workflow_variables.ref)),
        )

    def direct_refs(self) -> Iterator[core.ContextRef[core.Context] | core.ContextRef[facts.Scope]]:
        """Yield the direct references of the context, either to scopes or to other contexts."""
        yield self.workflow_context
        yield self.filesystem
        yield self.env
        yield self.job_variables


@dataclass(frozen=True)
class GitHubActionsStepContext(core.Context):
    """Context for a step within a job within a GitHub Actions Workflow."""

    #: Outer job context.
    job_context: core.ContextRef[GitHubActionsJobContext]
    #: Scope for environment variables (env block at step level)
    env: core.ContextRef[facts.Scope]
    #: Name prefix for step output variables (stored in the job variables)
    #: belonging to this step (e.g. "steps.step_id.outputs.")
    output_var_prefix: str | None

    @staticmethod
    def create(job_context: core.ContextRef[GitHubActionsJobContext], step_id: str | None) -> GitHubActionsStepContext:
        """Create a new step context and its associated scopes.

        Env scope inherits from outer context. Output var prefix is derived from step_id.

        Parameters
        ----------
        job_context: core.ContextRef[GitHubActionsJobContext]
            Outer job context.
        step_id: str | None
            Step id. If provided, used to derive name previx for step output variables.

        Returns
        -------
        GitHubActionsStepContext
            The new step context.
        """
        return GitHubActionsStepContext(
            job_context=job_context.get_non_owned(),
            env=core.OwningContextRef(facts.Scope("env", job_context.ref.env.ref)),
            output_var_prefix=("steps." + step_id + ".outputs.") if step_id is not None else None,
        )

    def direct_refs(self) -> Iterator[core.ContextRef[core.Context] | core.ContextRef[facts.Scope]]:
        """Yield the direct references of the context, either to scopes or to other contexts."""
        yield self.job_context
        yield self.env


class RawGitHubActionsWorkflowNode(core.InterpretationNode):
    """Interpretation node representing a GitHub Actions Workflow.

    Defines how to interpret a parsed workflow and generate its analysis representation.
    """

    #: Parsed workflow AST.
    definition: github_workflow_model.Workflow

    #: Workflow context
    context: core.ContextRef[GitHubActionsWorkflowContext]

    def __init__(
        self, definition: github_workflow_model.Workflow, context: core.ContextRef[GitHubActionsWorkflowContext]
    ) -> None:
        """Initialize node.

        Typically, construction should be done via the create function rather than using this constructor directly.
        """
        super().__init__()
        self.definition = definition
        self.context = context

    def identify_interpretations(self, state: core.State) -> dict[core.InterpretationKey, Callable[[], core.Node]]:
        """Interpret the workflow AST to generate control flow representation."""

        def build_workflow_node() -> core.Node:
            return GitHubActionsWorkflowNode.create(self.definition, self.context.get_non_owned())

        return {"default": build_workflow_node}

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the workflow name and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        if "name" in self.definition:
            result["workflow name"] = {(None, self.definition["name"])}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)

        return result

    @staticmethod
    def create(
        workflow: github_workflow_model.Workflow,
        analysis_context: core.ContextRef[core.AnalysisContext],
        source_filepath: str,
    ) -> RawGitHubActionsWorkflowNode:
        """Create workflow node and its associated context.

        Parameters
        ----------
        workflow: github_workflow_model.Workflow
            Parsed workflow AST.
        analysis_context: core.ContextRef[core.AnalysisContext]
            Outer analysis context.
        source_filepath: str
            Filepath of workflow file.

        Returns
        -------
        RawGitHubActionsWorkflowNode
            The new workflow node.
        """
        workflow_context = GitHubActionsWorkflowContext.create(analysis_context, source_filepath)

        return RawGitHubActionsWorkflowNode(workflow, core.OwningContextRef(workflow_context))


class GitHubActionsWorkflowNode(core.ControlFlowGraphNode):
    """Control-flow-graph node representing a GitHub Actions Workflow.

    Control flow structure executes each job in an arbitrary linear sequence
    (by default a topological sort satsifying the job dependencies). If an env block exists,
    it is applied beforehand.
    """

    #: Parsed workflow AST.
    definition: github_workflow_model.Workflow
    #: Workflow context.
    context: core.ContextRef[GitHubActionsWorkflowContext]
    #: Node to apply effects of env block, if any.
    env_block: RawGitHubActionsEnvNode | None
    #: Job nodes, identified by their job id.
    jobs: dict[str, RawGitHubActionsJobNode]
    #: List of job ids specifying job execution order.
    order: list[str]
    #: Control flow graph.
    _cfg: core.ControlFlowGraph

    def __init__(
        self,
        definition: github_workflow_model.Workflow,
        context: core.ContextRef[GitHubActionsWorkflowContext],
        env_block: RawGitHubActionsEnvNode | None,
        jobs: dict[str, RawGitHubActionsJobNode],
        order: list[str],
    ) -> None:
        """Initialize workflow node.

        Typically, construction should be done via the create function rather than using this constructor directly.

        Parameters
        ----------
        definition: github_workflow_model.Workflow
            Parsed workflow AST.
        context: core.ContextRef[GitHubActionsWorkflowContext]
            Workflow context.
        env_block: RawGitHubActionsEnvNode | None
            Node to apply effects of env block, if any.
        jobs: dict[str, RawGitHubActionsJobNode]
            List of job ids specifying job execution order.
        order: list[str]
            List of job ids specifying job execution order.
        """
        super().__init__()
        self.definition = definition
        self.context = context
        self.env_block = env_block
        self.jobs = jobs
        self.order = order

        self._cfg = core.ControlFlowGraph.create_from_sequence(
            list(filter(core.node_is_not_none, [self.env_block] + [self.jobs[job_id] for job_id in self.order]))
        )

    def children(self) -> Iterator[core.Node]:
        """Yield the child nodes of this node."""
        if self.env_block is not None:
            yield self.env_block
        for job_id in self.order:
            yield self.jobs[job_id]

    def get_entry(self) -> core.Node:
        """Return the entry node."""
        return self._cfg.get_entry()

    def get_successors(self, node: core.Node, exit_type: core.ExitType) -> set[core.Node | core.ExitType]:
        """Return the successors for a particular exit of a particular node."""
        return self._cfg.get_successors(node, core.DEFAULT_EXIT)

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the workflow name and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        if "name" in self.definition:
            result["workflow name"] = {(None, self.definition["name"])}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)

        return result

    @staticmethod
    def _find_job_id_case_insensitive(jobs: dict[str, RawGitHubActionsJobNode], job_id: str) -> str | None:
        if job_id in jobs:
            return job_id
        for actual_job_id in jobs:
            if actual_job_id.lower() == job_id.lower():
                return actual_job_id
        return None

    @staticmethod
    def create(
        workflow: github_workflow_model.Workflow, context: core.NonOwningContextRef[GitHubActionsWorkflowContext]
    ) -> GitHubActionsWorkflowNode:
        """Create workflow node from workflow AST.

        Also creates a job node for each job, and performs a topological sort of the job dependency graph
        to choose an arbitrary valid sequential execution order.

        Parameters
        ----------
        workflow: github_workflow_model.Workflow
            Parsed workflow AST.
        context: core.NonOwningContextRef[GitHubActionsWorkflowContext]
            Workflow context.

        Returns
        -------
        GitHubActionsWorkflowNode
            The new workflow node.
        """
        jobs: dict[str, RawGitHubActionsJobNode] = {}

        for job_id, job in workflow["jobs"].items():
            job_node = RawGitHubActionsJobNode(
                job, job_id, core.OwningContextRef(GitHubActionsJobContext.create(context))
            )
            jobs[job_id] = job_node

        dependency_graph: dict[str, list[str]] = {}
        for job_id, job_node in jobs.items():
            edges: list[str] = []
            if "needs" in job_node.definition:
                needs = job_node.definition["needs"]
                if isinstance(needs, list):
                    for need in needs:
                        actual_need = GitHubActionsWorkflowNode._find_job_id_case_insensitive(jobs, need)
                        if actual_need is None:
                            raise CallGraphError("needs refers to invalid job")
                        edges.append(actual_need)
                elif isinstance(needs, str):
                    actual_need = GitHubActionsWorkflowNode._find_job_id_case_insensitive(jobs, needs)
                    if actual_need is None:
                        raise CallGraphError("needs refers to invalid job")
                    edges.append(actual_need)

            dependency_graph[job_id] = edges

        ts = TopologicalSorter(dependency_graph)
        order = list(ts.static_order())

        env_block = None
        if "env" in workflow:
            env_block = RawGitHubActionsEnvNode(workflow["env"], context)

        return GitHubActionsWorkflowNode(workflow, context, env_block, jobs, order)


class RawGitHubActionsJobNode(core.InterpretationNode):
    """Interpretation node representing a GitHub Actions Job.

    Defines how to interpret the different kinds of jobs (normal jobs, reusable workflow call jobs),
    and generate their analysis representation.
    """

    #: Parsed job AST.
    definition: github_workflow_model.Job
    #: Job id.
    job_id: str
    #: Job context.
    context: core.ContextRef[GitHubActionsJobContext]

    def __init__(
        self, definition: github_workflow_model.Job, job_id: str, context: core.ContextRef[GitHubActionsJobContext]
    ) -> None:
        """Initialize node."""
        super().__init__()
        self.definition = definition
        self.job_id = job_id
        self.context = context

    def identify_interpretations(self, state: core.State) -> dict[core.InterpretationKey, Callable[[], core.Node]]:
        """Interpret job AST to generate representation for either a normal job or a reusable workflow call job."""
        if github_workflow_model.is_normal_job(self.definition):
            normal_job_definition = self.definition

            def build_normal_job() -> core.Node:
                return GitHubActionsNormalJobNode.create(
                    normal_job_definition, self.job_id, self.context.get_non_owned()
                )

            return {"default": build_normal_job}
        if github_workflow_model.is_reusable_workflow_call_job(self.definition):
            raw_with_params = self.definition.get("with", {})
            call_def = self.definition
            if isinstance(raw_with_params, dict):

                def build_reusable_workflow_call_job() -> core.Node:
                    uses_name, _, uses_version = call_def["uses"].rpartition("@")

                    with_parameters: dict[str, facts.Value] = {}
                    for key, val in raw_with_params.items():
                        if isinstance(val, str):
                            parsed_val = github_expr.extract_value_from_expr_string(
                                val, self.context.ref.job_variables.ref
                            )
                            if parsed_val is not None:
                                with_parameters[key] = parsed_val
                        elif isinstance(val, bool):
                            with_parameters[key] = facts.StringLiteral("true") if val else facts.StringLiteral("false")
                        else:
                            with_parameters[key] = facts.StringLiteral(str(val))

                    return GitHubActionsReusableWorkflowCallNode(
                        call_def,
                        self.job_id,
                        self.context.get_non_owned(),
                        uses_name,
                        uses_version if uses_version != "" else None,
                        with_parameters,
                    )

                return {"default": build_reusable_workflow_call_job}

            def build_noop() -> core.Node:
                return core.NoOpStatementNode()

            return {"default": build_noop}

        raise CallGraphError("invalid job")

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the job id and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        result["job id"] = {(None, self.job_id)}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)

        return result


class GitHubActionsNormalJobNode(core.ControlFlowGraphNode):
    """Control-flow-graph node representing a GitHub Actions Normal Job.

    Control flow structure executes each step in the order defined by the job,
    preceded by applying the effects of the matrix and env blocks if they exist
    and succeeded by applying the effects of the output block if it exists.
    (TODO generating output block not yet implemented).
    """

    #: Parsed job AST.
    definition: github_workflow_model.NormalJob
    #: Job id.
    job_id: str
    #: Node to apply effects of matrix block, if any.
    matrix_block: RawGitHubActionsMatrixNode | None
    #: Node to apply effects of env block, if any.
    env_block: RawGitHubActionsEnvNode | None
    #: Step nodes, in execution order.
    steps: list[RawGitHubActionsStepNode]
    #: Node to apply effects of output block, if any.
    output_block: core.Node | None  # TODO More specific
    #: Job context
    context: core.ContextRef[GitHubActionsJobContext]
    #: Control flow graph
    _cfg: core.ControlFlowGraph

    def __init__(
        self,
        definition: github_workflow_model.NormalJob,
        job_id: str,
        matrix_block: RawGitHubActionsMatrixNode | None,
        env_block: RawGitHubActionsEnvNode | None,
        steps: list[RawGitHubActionsStepNode],
        output_block: core.Node | None,
        context: core.ContextRef[GitHubActionsJobContext],
    ) -> None:
        """Initialize job node.

        Typically, construction should be done via the create function rather than using this constructor directly.

        Parameters
        ----------
        definition: github_workflow_model.NormalJob
            Parsed job AST.
        job_id: str
            Job id.
        matrix_block: RawGitHubActionsMatrixNode | None
            Node to apply effects of matrix block, if any.
        env_block: RawGitHubActionsEnvNode | None
            Node to apply effects of env block, if any.
        steps: list[RawGitHubActionsStepNode]
            Step nodes, in execution order.
        output_block: core.Node | None,
            Node to apply effects of output block, if any.
        context: core.ContextRef[GitHubActionsJobContext]
            Job context.
        """
        super().__init__()
        self.definition = definition
        self.job_id = job_id
        self.matrix_block = matrix_block
        self.env_block = env_block
        self.steps = steps
        self.output_block = output_block
        self.context = context

        self._cfg = core.ControlFlowGraph.create_from_sequence(
            list(filter(core.node_is_not_none, [self.matrix_block, self.env_block] + self.steps + [self.output_block]))
        )

    def children(self) -> Iterator[core.Node]:
        """Yield the child nodes of this node."""
        if self.matrix_block is not None:
            yield self.matrix_block
        if self.env_block is not None:
            yield self.env_block
        yield from self.steps
        if self.output_block is not None:
            yield self.output_block

    def get_entry(self) -> core.Node:
        """Return the entry node."""
        return self._cfg.get_entry()

    def get_successors(self, node: core.Node, exit_type: core.ExitType) -> set[core.Node | core.ExitType]:
        """Return the successors for a particular exit of a particular node."""
        return self._cfg.get_successors(node, core.DEFAULT_EXIT)

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the job id and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        result["job id"] = {(None, self.job_id)}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result

    @staticmethod
    def create(
        job: github_workflow_model.NormalJob, job_id: str, context: core.NonOwningContextRef[GitHubActionsJobContext]
    ) -> GitHubActionsNormalJobNode:
        """Create normal job node from job AST. Also creates a step node for each step.

        Parameters
        ----------
        job: github_workflow_model.NormalJob
            Parsed job AST.
        job_id: str
            Job id.
        context: core.NonOwningContextRef[GitHubActionsJobContext]
            Job context.

        Returns
        -------
        GitHubActionsNormalJobNode
            The new job node.
        """
        # TODO output block

        matrix_block = None
        if "strategy" in job and "matrix" in job["strategy"]:
            matrix_block = RawGitHubActionsMatrixNode(job["strategy"]["matrix"], context)

        env_block = None
        if "env" in job:
            env_block = RawGitHubActionsEnvNode(job["env"], context)

        steps = [
            RawGitHubActionsStepNode(
                step, core.OwningContextRef(GitHubActionsStepContext.create(context, step.get("id")))
            )
            for step in job.get("steps", [])
        ]

        return GitHubActionsNormalJobNode(job, job_id, matrix_block, env_block, steps, None, context)


class GitHubActionsReusableWorkflowCallNode(core.InterpretationNode):
    """Interpretation node representing a GitHub Actions Reusable Workflow Call Job.

    Defines how to interpret the semantics of different supported reusable workflows that may
    be invoked (TODO currently none are supported).
    """

    #: Parsed reusable workflow call AST.
    definition: github_workflow_model.ReusableWorkflowCallJob
    #: Job id.
    job_id: str
    #: Job context.
    context: core.ContextRef[GitHubActionsJobContext]

    #: Name of the reusable workflow being invoked (without version component).
    uses_name: str
    #: Version of the reusable workflow being invoked (if specified).
    uses_version: str | None

    #: Input parameters specified for reusable workflow.
    with_parameters: dict[str, facts.Value]

    def __init__(
        self,
        definition: github_workflow_model.ReusableWorkflowCallJob,
        job_id: str,
        context: core.ContextRef[GitHubActionsJobContext],
        uses_name: str,
        uses_version: str | None,
        with_parameters: dict[str, facts.Value],
    ) -> None:
        """Initialize reusable workflow call node.

        Parameters
        ----------
        definition: github_workflow_model.ReusableWorkflowCallJob
            Parsed reusable workflow call AST.
        job_id: str
            Job id.
        context: core.ContextRef[GitHubActionsJobContext]
            Job context.
        uses_name: str
            Name of the reusable workflow being invoked (without version component).
        uses_version: str | None
            Version of the reusable workflow being invoked (if specified).
        with_parameters: dict[str, facts.Value]
            Input parameters specified for reusable workflow.
        """
        super().__init__()
        self.definition = definition
        self.job_id = job_id
        self.context = context
        self.uses_name = uses_name
        self.uses_version = uses_version
        self.with_parameters = with_parameters

    def identify_interpretations(self, state: core.State) -> dict[core.InterpretationKey, Callable[[], core.Node]]:
        """Intepret the semantics of the different supported reusable workflows.

        (TODO currently none are supported).
        """

        def build_noop() -> core.Node:
            return core.NoOpStatementNode()

        return {"default": build_noop}

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table.

        Contains the job id, reusable workflow name, and scopes.
        """
        result: dict[str, set[tuple[str | None, str]]] = {}
        result["job id"] = {(None, self.job_id)}
        result["uses"] = {(None, self.definition["uses"])}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)

        return result


class RawGitHubActionsStepNode(core.InterpretationNode):
    """Interpretation node representing a GitHub Actions Step.

    Defines how to interpret the different kinds of steps (run jobs, action steps),
    and generate their analysis representation.
    """

    #: Parsed step AST.
    definition: github_workflow_model.Step
    #: Step context
    context: core.ContextRef[GitHubActionsStepContext]

    def __init__(
        self, definition: github_workflow_model.Step, context: core.ContextRef[GitHubActionsStepContext]
    ) -> None:
        """Intitialize node."""
        super().__init__()
        self.definition = definition
        self.context = context

    def identify_interpretations(self, state: core.State) -> dict[core.InterpretationKey, Callable[[], core.Node]]:
        """Interpret step AST to generate representation depending on whether it is a run step or an action step."""
        if github_workflow_model.is_action_step(self.definition):
            action_step_definition = self.definition

            def build_action_step() -> core.Node:
                return RawGitHubActionsActionStepNode(action_step_definition, self.context.get_non_owned())

            return {"default": build_action_step}
        if github_workflow_model.is_run_step(self.definition):
            run_step_definition = self.definition

            def build_run_step() -> core.Node:
                return GitHubActionsRunStepNode.create(run_step_definition, self.context.get_non_owned())

            return {"default": build_run_step}
        raise CallGraphError("invalid step")

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table.

        Contains the step id, name, action name (if action step), and scopes.
        """
        result: dict[str, set[tuple[str | None, str]]] = {}
        if "id" in self.definition:
            result["step id"] = {(None, self.definition["id"])}
        elif "name" in self.definition:
            result["step name"] = {(None, self.definition["name"])}
        if github_workflow_model.is_action_step(self.definition):
            result["step uses"] = {(None, self.definition["uses"])}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)

        return result


class RawGitHubActionsActionStepNode(core.InterpretationNode):
    """Interpretation node representing a GitHub Actions Action Step.

    Defines how to extract the name, version and parameters used to invoke the action,
    and generate a node with those details resolved for further interpretation.
    """

    #: Parsed step AST.
    definition: github_workflow_model.ActionStep
    #: Step context.
    context: core.ContextRef[GitHubActionsStepContext]

    def __init__(
        self, definition: github_workflow_model.ActionStep, context: core.ContextRef[GitHubActionsStepContext]
    ) -> None:
        """Initialize node."""
        super().__init__()
        self.definition = definition
        self.context = context

    def identify_interpretations(self, state: core.State) -> dict[core.InterpretationKey, Callable[[], core.Node]]:
        """Intepret action step AST to extract the name, version and parameters."""
        raw_with_params = self.definition.get("with", {})
        if isinstance(raw_with_params, dict):

            def build_action() -> core.Node:
                uses_name, _, uses_version = self.definition["uses"].rpartition("@")

                with_parameters: dict[str, facts.Value] = {}
                for key, val in raw_with_params.items():
                    if isinstance(val, str):
                        parsed_val = github_expr.extract_value_from_expr_string(
                            val, self.context.ref.job_context.ref.job_variables.ref
                        )
                        if parsed_val is not None:
                            with_parameters[key] = parsed_val
                    elif isinstance(val, bool):
                        with_parameters[key] = facts.StringLiteral("true") if val else facts.StringLiteral("false")
                    else:
                        with_parameters[key] = facts.StringLiteral(str(val))

                return GitHubActionsActionStepNode(
                    self.definition,
                    self.context.get_non_owned(),
                    uses_name,
                    uses_version if uses_version != "" else None,
                    with_parameters,
                )

            return {"default": build_action}

        def build_noop() -> core.Node:
            return core.NoOpStatementNode()

        return {"default": build_noop}

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the step id, name, action name, and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        if "id" in self.definition:
            result["step id"] = {(None, self.definition["id"])}
        elif "name" in self.definition:
            result["step name"] = {(None, self.definition["name"])}
        result["step uses"] = {(None, self.definition["uses"])}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)

        return result


class GitHubActionsActionStepNode(core.InterpretationNode):
    """Interpretation node representing a GitHub Actions Action Step.

    Defines how to interpret the semantics of different supported actions that may
    be invoked.
    """

    #: Parsed step AST.
    definition: github_workflow_model.ActionStep
    #: Step context.
    context: core.ContextRef[GitHubActionsStepContext]

    #: Name of the action being invoked (without version component).
    uses_name: str
    #: Version of the action being invoked (if specified).
    uses_version: str | None

    #: Input parameters specified for action.
    with_parameters: dict[str, facts.Value]

    def __init__(
        self,
        definition: github_workflow_model.ActionStep,
        context: core.ContextRef[GitHubActionsStepContext],
        uses_name: str,
        uses_version: str | None,
        with_parameters: dict[str, facts.Value],
    ) -> None:
        """Initialize action step node.

        Parameters
        ----------
        definition: github_workflow_model.ActionStep
            Parsed step AST.
        context: core.ContextRef[GitHubActionsStepContext]
            Step context.
        uses_name: str
            Name of the action being invoked (without version component).
        uses_version: str | None
            Version of the action being invoked (if specified).
        with_parameters: dict[str, facts.Value]
            Input parameters specified for action.
        """
        super().__init__()
        self.definition = definition
        self.context = context
        self.uses_name = uses_name
        self.uses_version = uses_version
        self.with_parameters = with_parameters

    def identify_interpretations(self, state: core.State) -> dict[core.InterpretationKey, Callable[[], core.Node]]:
        """Intepret the semantics of the different supported actions."""
        match self.uses_name:
            case "actions/checkout":

                def build_checkout() -> core.Node:
                    return models.GitHubActionsGitCheckoutModelNode()

                return {"default": build_checkout}
            case "actions/setup-java":
                # Installs Java toolchain
                def build_setup_java() -> core.Node:
                    return models.InstallPackageNode(
                        install_scope=self.context.ref.job_context.ref.filesystem.ref,
                        name=facts.StringLiteral("java"),
                        version=self.with_parameters.get("java-version", facts.StringLiteral("")),
                        distribution=self.with_parameters.get("distribution", facts.StringLiteral("")),
                        url=facts.StringLiteral("https://github.com/actions/setup-java"),
                    )

                return {"default": build_setup_java}
            case "graalvm/setup-graalvm":
                # Installs Java toolchain
                def build_setup_graalvm() -> core.Node:
                    return models.InstallPackageNode(
                        install_scope=self.context.ref.job_context.ref.filesystem.ref,
                        name=facts.StringLiteral("java"),
                        version=self.with_parameters.get("java-version", facts.StringLiteral("")),
                        distribution=self.with_parameters.get("distribution", facts.StringLiteral("graalvm")),
                        url=facts.StringLiteral("https://github.com/graalvm/setup-graalvm"),
                    )

                return {"default": build_setup_graalvm}

            case "oracle-actions/setup-java":
                # Installs Java toolchain
                def build_setup_oracle_java() -> core.Node:
                    return models.InstallPackageNode(
                        install_scope=self.context.ref.job_context.ref.filesystem.ref,
                        name=facts.StringLiteral("java"),
                        version=self.with_parameters.get("release", facts.StringLiteral("")),
                        distribution=self.with_parameters.get("website", facts.StringLiteral("oracle.com")),
                        url=facts.StringLiteral("https://github.com/oracle-actions/setup-java"),
                    )

                return {"default": build_setup_oracle_java}
            case "actions/setup-python":
                # Installs Python toolchain
                def build_setup_python() -> core.Node:
                    return models.InstallPackageNode(
                        install_scope=self.context.ref.job_context.ref.filesystem.ref,
                        name=facts.StringLiteral("python"),
                        version=self.with_parameters.get("python-version", facts.StringLiteral("")),
                        distribution=facts.StringLiteral(""),
                        url=facts.StringLiteral(""),
                    )

                return {"default": build_setup_python}
            case "actions/upload-artifact":
                # Uploads artifact to pipeline artifact storage.
                if "name" in self.with_parameters and "path" in self.with_parameters:
                    split = evaluation.parse_str_expr_split(self.with_parameters["path"], "\n")
                    if len(split) == 1:

                        def build_upload_artifact() -> core.Node:
                            return models.GitHubActionsUploadArtifactModelNode(
                                artifacts_scope=self.context.ref.job_context.ref.workflow_context.ref.artifacts.ref,
                                artifact_name=self.with_parameters["name"],
                                artifact_file=facts.UnaryStringOp(facts.UnaryStringOperator.BASENAME, split[0]),
                                filesystem_scope=self.context.ref.job_context.ref.filesystem.ref,
                                path=split[0],
                            )

                        return {"default": build_upload_artifact}

                    def build_multiple_upload_artifact() -> core.Node:
                        seq: list[core.Node] = [
                            models.GitHubActionsUploadArtifactModelNode(
                                artifacts_scope=self.context.ref.job_context.ref.workflow_context.ref.artifacts.ref,
                                artifact_name=self.with_parameters["name"],
                                artifact_file=facts.UnaryStringOp(facts.UnaryStringOperator.BASENAME, path),
                                filesystem_scope=self.context.ref.job_context.ref.filesystem.ref,
                                path=path,
                            )
                            for path in [x for x in split if x != facts.StringLiteral("")]
                        ]
                        if len(seq) == 0:
                            return core.NoOpStatementNode()
                        return core.SimpleSequence(seq)

                    return {"default": build_multiple_upload_artifact}

            case "actions/download-artifact":
                # Downloads artifact from pipeline artifact storage.
                if "name" in self.with_parameters:

                    def build_download_artifact() -> core.Node:
                        return models.GitHubActionsDownloadArtifactModelNode(
                            artifacts_scope=self.context.ref.job_context.ref.workflow_context.ref.artifacts.ref,
                            artifact_name=self.with_parameters["name"],
                            filesystem_scope=self.context.ref.job_context.ref.filesystem.ref,
                        )

                    return {"default": build_download_artifact}
            case "softprops/action-gh-release":
                # Creates a GitHub release.
                if "files" in self.with_parameters:
                    split = evaluation.parse_str_expr_split(self.with_parameters["files"], "\n")
                    if len(split) == 1:

                        def build_upload_release() -> core.Node:
                            return models.GitHubActionsReleaseModelNode(
                                artifacts_scope=self.context.ref.job_context.ref.workflow_context.ref.releases.ref,
                                artifact_name=facts.StringLiteral(str(id(self))),
                                artifact_file=facts.UnaryStringOp(facts.UnaryStringOperator.BASENAME, split[0]),
                                filesystem_scope=self.context.ref.job_context.ref.filesystem.ref,
                                path=split[0],
                            )

                        return {"default": build_upload_release}

                    def build_multiple_upload_release() -> core.Node:
                        return core.SimpleSequence(
                            [
                                models.GitHubActionsReleaseModelNode(
                                    artifacts_scope=self.context.ref.job_context.ref.workflow_context.ref.releases.ref,
                                    artifact_name=facts.StringLiteral(str(id(self))),
                                    artifact_file=facts.UnaryStringOp(facts.UnaryStringOperator.BASENAME, path),
                                    filesystem_scope=self.context.ref.job_context.ref.filesystem.ref,
                                    path=path,
                                )
                                for path in [x for x in split if x != facts.StringLiteral("")]
                            ]
                        )

                    return {"default": build_multiple_upload_release}

        def build_noop() -> core.Node:
            return core.NoOpStatementNode()

        return {"default": build_noop}

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the step id, name, action name, with parameters, and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        if "id" in self.definition:
            result["step id"] = {(None, self.definition["id"])}
        elif "name" in self.definition:
            result["step_name"] = {(None, self.definition["name"])}
        result["step uses"] = {(None, self.definition["uses"])}

        for key, val in self.with_parameters.items():
            result["with(" + key + ")"] = {(None, val.to_datalog_fact_string())}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)

        return result


class GitHubActionsRunStepNode(core.ControlFlowGraphNode):
    """Control-flow-graph node representing a GitHub Actions Run Step.

    Control flow structure executes the shell script defined by the step.
    If an env block exists, it is applied beforehand.
    """

    #: Parsed step AST.
    definition: github_workflow_model.RunStep
    #: Node to apply effects of env block, if any.
    env_block: RawGitHubActionsEnvNode | None
    #: Shell script to be run.
    shell_block: bash.RawBashScriptNode
    #: Step context.
    context: core.ContextRef[GitHubActionsStepContext]
    #: Control flow graph
    _cfg: core.ControlFlowGraph

    def __init__(
        self,
        definition: github_workflow_model.RunStep,
        env_block: RawGitHubActionsEnvNode | None,
        shell_block: bash.RawBashScriptNode,
        context: core.ContextRef[GitHubActionsStepContext],
    ) -> None:
        """Initialize run step node.

        Typically, construction should be done via the create function rather than using this constructor directly.

        Parameters
        ----------
        definition: github_workflow_model.RunStep
            Parsed step AST.
        env_block: RawGitHubActionsEnvNode | None
            Node to apply effects of env block, if any.
        shell_block: bash.RawBashScriptNode
            Shell script to be run.
        context: core.ContextRef[GitHubActionsStepContext]
            Step context.
        """
        super().__init__()
        self.definition = definition
        self.env_block = env_block
        self.shell_block = shell_block
        self.context = context

        self._cfg = core.ControlFlowGraph.create_from_sequence(
            list(filter(core.node_is_not_none, [self.env_block, self.shell_block]))
        )

    def children(self) -> Iterator[core.Node]:
        """Yield the child nodes of this node."""
        if self.env_block is not None:
            yield self.env_block
        yield self.shell_block

    def get_entry(self) -> core.Node:
        """Return the entry node."""
        return self._cfg.get_entry()

    def get_successors(self, node: core.Node, exit_type: core.ExitType) -> set[core.Node | core.ExitType]:
        """Return the successors for a particular exit of a particular node."""
        return self._cfg.get_successors(node, core.DEFAULT_EXIT)

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the step id, name, and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        if "id" in self.definition:
            result["step id"] = {(None, self.definition["id"])}
        elif "name" in self.definition:
            result["step name"] = {(None, self.definition["name"])}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result

    @staticmethod
    def create(
        run_step: github_workflow_model.RunStep, context: core.NonOwningContextRef[GitHubActionsStepContext]
    ) -> GitHubActionsRunStepNode:
        """Create run step node from step AST.

        Parameters
        ----------
        run_step: github_workflow_model.RunStep
            Parsed step AST.
        context: core.NonOwningContextRef[GitHubActionsStepContext]
            Step context.

        Returns
        -------
        GitHubActionsRunStepNode
            The new run step node.
        """
        env_block = None
        if "env" in run_step:
            env_block = RawGitHubActionsEnvNode(run_step["env"], context)
        script_node = bash.RawBashScriptNode(
            facts.StringLiteral(run_step["run"]),
            core.OwningContextRef(bash.BashScriptContext.create_from_run_step(context, "")),
        )
        return GitHubActionsRunStepNode(run_step, env_block, script_node, context)


class RawGitHubActionsEnvNode(core.InterpretationNode):
    """Interpretation node representing an env block in a GitHub Actions Workflow/Job/Step.

    Defines how to interpret the declarative env block to generate imperative constructs to
    write the values to the env variables.
    """

    #: Parsed env block AST.
    definition: github_workflow_model.Env
    #: Outer context.
    context: core.ContextRef[GitHubActionsWorkflowContext | GitHubActionsJobContext | GitHubActionsStepContext]

    def __init__(
        self,
        definition: github_workflow_model.Env,
        context: core.ContextRef[GitHubActionsWorkflowContext | GitHubActionsJobContext | GitHubActionsStepContext],
    ) -> None:
        """Initialize env block node.

        Parameters
        ----------
        definition: github_workflow_model.Env
            Parsed env block AST.
        context: core.ContextRef[GitHubActionsWorkflowContext | GitHubActionsJobContext | GitHubActionsStepContext]
            Outer context.
        """
        super().__init__()
        self.definition = definition
        self.context = context

    def identify_interpretations(self, state: core.State) -> dict[core.InterpretationKey, Callable[[], core.Node]]:
        """Interpret declarative env block to generate imperative constructs to write to the env vars."""
        env = self.definition
        if isinstance(env, dict):

            def build_env_writes() -> core.Node:
                env_writes: dict[str, facts.Value] = {}
                for key, val in env.items():
                    if isinstance(val, str):
                        var_scope = (
                            self.context.ref.job_context.ref.job_variables.ref
                            if isinstance(self.context.ref, GitHubActionsStepContext)
                            else (
                                self.context.ref.job_variables.ref
                                if isinstance(self.context.ref, GitHubActionsJobContext)
                                else None
                            )
                        )
                        parsed_val = github_expr.extract_value_from_expr_string(val, var_scope)
                        if parsed_val is not None:
                            env_writes[key] = parsed_val
                    elif isinstance(val, bool):
                        env_writes[key] = facts.StringLiteral("true") if val else facts.StringLiteral("false")
                    else:
                        env_writes[key] = facts.StringLiteral(str(val))

                if len(env_writes) == 0:
                    return core.NoOpStatementNode()

                return core.SimpleSequence(
                    [
                        models.VarAssignNode(
                            models.VarAssignKind.GITHUB_ENV_VAR, self.context.ref.env.ref, facts.StringLiteral(var), val
                        )
                        for var, val in env_writes.items()
                    ]
                )

            return {"default": build_env_writes}

        def build_noop() -> core.Node:
            return core.NoOpStatementNode()

        return {"default": build_noop}

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result


class RawGitHubActionsMatrixNode(core.InterpretationNode):
    """Interpretation node representing a matrix block in a GitHub Actions Job.

    Defines how to interpret the declarative matrix block to generate imperative constructs to
    write the values to the matrix variables.
    """

    #: Parsed matrix block AST.
    definition: github_workflow_model.Matrix
    #: Outer job context.
    context: core.ContextRef[GitHubActionsJobContext]

    def __init__(
        self,
        definition: github_workflow_model.Matrix,
        context: core.ContextRef[GitHubActionsJobContext],
    ) -> None:
        """Initialize matrix node.

        Parameters
        ----------
        definition: github_workflow_model.Matrix
            Parsed matrix block AST.
        context: core.ContextRef[GitHubActionsJobContext]
            Outer job context.
        """
        super().__init__()
        self.definition = definition
        self.context = context

    def identify_interpretations(self, state: core.State) -> dict[core.InterpretationKey, Callable[[], core.Node]]:
        """Interpret declarative matrix block to generate imperative constructs to write to the matrix variables."""
        matrix = self.definition
        if isinstance(matrix, dict):

            def build_matrix_writes() -> core.Node:
                matrix_writes: dict[str, list[facts.Value]] = defaultdict(list)
                if isinstance(matrix, dict):
                    for key, vals in matrix.items():
                        if isinstance(vals, list):
                            var_scope = self.context.ref.job_variables.ref

                            for val in vals:
                                if isinstance(val, str):
                                    parsed_val = github_expr.extract_value_from_expr_string(val, var_scope)
                                    if parsed_val is not None:
                                        matrix_writes[key].append(parsed_val)
                                elif isinstance(val, bool):
                                    matrix_writes[key].append(
                                        facts.StringLiteral("true") if val else facts.StringLiteral("false")
                                    )
                                else:
                                    matrix_writes[key].append(facts.StringLiteral(str(val)))

                if len(matrix_writes) == 0:
                    return core.NoOpStatementNode()

                return core.SimpleSequence(
                    [
                        core.SimpleAlternatives(
                            [
                                models.VarAssignNode(
                                    models.VarAssignKind.GITHUB_JOB_VAR,
                                    self.context.ref.job_variables.ref,
                                    facts.StringLiteral("matrix." + key),
                                    val,
                                )
                                for val in vals
                            ]
                        )
                        for key, vals in matrix_writes.items()
                    ]
                )

            return {"default": build_matrix_writes}

        def build_noop() -> core.Node:
            return core.NoOpStatementNode()

        return {"default": build_noop}

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result
