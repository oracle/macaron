# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Entry points to perform and use the dataflow analysis."""

from __future__ import annotations

from collections.abc import Iterable

from macaron.code_analyzer.dataflow_analysis import bash, core, evaluation, facts, github, printing
from macaron.errors import CallGraphError
from macaron.parsers import actionparser, github_workflow_model
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, BuildToolCommand


def analyse_github_workflow_file(workflow_path: str, repo_path: str | None, dump_debug: bool = False) -> core.Node:
    """Perform dataflow analysis for GitHub Actions Workflow file.

    Parameters
    ----------
    workflow_path: str
        The path to workflow file.
    repo_path: str | None
        The path to the repo.
    dump_debug: bool
        Whether to output debug dot file (in the current working directory).

    Returns
    -------
    core.Node
        Graph representation of workflow and analysis results.
    """
    workflow = actionparser.parse(workflow_path)

    analysis_context = core.OwningContextRef(core.AnalysisContext(repo_path))

    core.reset_debug_sequence_number()
    raw_workflow_node = github.RawGitHubActionsWorkflowNode.create(workflow, analysis_context, workflow_path)
    core.increment_debug_sequence_number()

    raw_workflow_node.analyse()

    if dump_debug:
        with open("analysis." + workflow_path.replace("/", "_") + ".dot", "w", encoding="utf-8") as f:
            printing.print_as_dot_graph(raw_workflow_node, f, include_properties=True, include_states=True)

    return raw_workflow_node


def analyse_github_workflow(
    workflow: github_workflow_model.Workflow, workflow_source_path: str, repo_path: str | None, dump_debug: bool = False
) -> core.Node:
    """Perform dataflow analysis for GitHub Actions Workflow.

    Parameters
    ----------
    workflow: github_workflow_model.Workflow
        The workflow.
    workflow_path: str
        The source path for the workflow.
    repo_path: str | None
        The path to the repo.
    dump_debug: bool
        Whether to output debug dot file (in the current working directory).

    Returns
    -------
    core.Node
        Graph representation of workflow and analysis results.
    """
    analysis_context = core.OwningContextRef(core.AnalysisContext(repo_path))

    core.reset_debug_sequence_number()
    raw_workflow_node = github.RawGitHubActionsWorkflowNode.create(workflow, analysis_context, workflow_source_path)
    core.increment_debug_sequence_number()

    raw_workflow_node.analyse()

    if dump_debug:
        with open("analysis." + workflow_source_path.replace("/", "_") + ".dot", "w", encoding="utf-8") as f:
            printing.print_as_dot_graph(raw_workflow_node, f, include_properties=True, include_states=True)

    return raw_workflow_node


def analyse_bash_script(
    bash_content: str, source_path: str, repo_path: str | None, dump_debug: bool = False
) -> core.Node:
    """Perform dataflow analysis for Bash script.

    Parameters
    ----------
    bash_content: str
        The Bash script content.
    source_path: str
        The source path for the Bash script.
    repo_path: str | None
        The path to the repo.
    dump_debug: bool
        Whether to output debug dot file (in the current working directory).

    Returns
    -------
    core.Node
        Graph representation of Bash script and analysis results.
    """
    analysis_context = core.OwningContextRef(core.AnalysisContext(repo_path))
    bash_context = core.OwningContextRef(bash.BashScriptContext.create_in_isolation(analysis_context, source_path))
    core.reset_debug_sequence_number()
    bash_node = bash.RawBashScriptNode(facts.StringLiteral(bash_content), bash_context)
    core.increment_debug_sequence_number()

    bash_node.analyse()

    if dump_debug:
        with open(
            "analysis." + source_path.replace("/", "_") + "." + str(hash(bash_content)) + ".dot", "w", encoding="utf-8"
        ) as f:
            printing.print_as_dot_graph(bash_node, f, include_properties=True, include_states=True)

    return bash_node


# TODO generalise visitors
class FindSecretsVisitor:
    """Visitor to find references to GitHub secrets in analysis expressions."""

    #: Scope in which secrets may be found
    workflow_var_scope: facts.Scope
    #: Found secret variable names, populated by running the visitor
    secrets: set[str]

    def __init__(self, workflow_var_scope: facts.Scope) -> None:
        """Construct a visitor to find secrets.

        Parameters
        ----------
        workflow_var_scope: facts.Scope
            Scope in which secrets may be found
        """
        self.workflow_var_scope = workflow_var_scope
        self.secrets = set()

    def visit_value(self, value: facts.Value) -> None:
        """Search value expression for secrets."""
        match value:
            case facts.StringLiteral(_):
                return
            case facts.Read(loc):
                self.visit_location(loc)
                if evaluation.scope_matches(loc.scope, self.workflow_var_scope):
                    match loc.loc:
                        case facts.Variable(facts.StringLiteral(name)):
                            if name.startswith("secrets."):
                                self.secrets.add(name[len("secrets.") :])
                return
            case facts.ArbitraryNewData(_):
                return
            case facts.UnaryStringOp(_, operand):
                self.visit_value(operand)
                return
            case facts.BinaryStringOp(_, operand1, operand2):
                self.visit_value(operand1)
                self.visit_value(operand2)
                return
            case facts.ParameterPlaceholderValue(name):
                return
            case facts.InstalledPackage(name, version, distribution, url):
                self.visit_value(name)
                self.visit_value(version)
                self.visit_value(distribution)
                self.visit_value(url)
                return
            case facts.Symbolic(sym_val):
                self.visit_value(sym_val)
                return
        raise CallGraphError("unknown facts.Value type: " + value.__class__.__name__)

    def visit_location(self, location: facts.Location) -> None:
        """Search location expression for secrets."""
        self.visit_location_specifier(location.loc)

    def visit_location_specifier(self, location: facts.LocationSpecifier) -> None:
        """Search location expression for secrets."""
        match location:
            case facts.Filesystem(path):
                self.visit_value(path)
                return
            case facts.Variable(name):
                self.visit_value(name)
                return
            case facts.Artifact(name, file):
                self.visit_value(name)
                self.visit_value(file)
                return
            case facts.FilesystemAnyUnderDir(path):
                self.visit_value(path)
                return
            case facts.ArtifactAnyFilename(name):
                self.visit_value(name)
                return
            case facts.ParameterPlaceholderLocation(name):
                return
            case facts.Console():
                return
            case facts.Installed(name):
                self.visit_value(name)
                return
        raise CallGraphError("unknown location type: " + location.__class__.__name__)


def get_reachable_secrets(bash_cmd_node: bash.BashSingleCommandNode) -> set[str]:
    """Get GitHub secrets that are reachable at a bash command.

    Parameters
    ----------
    bash_cmd_node: bash.BashSingleCommandNode
        The target Bash command node.

    Returns
    -------
    set[str]
        The set of reachable secret variable names.
    """
    result: set[str] = set()
    github_context = bash_cmd_node.context.ref.get_containing_github_context()
    if github_context is None:
        return result
    env_scope = bash_cmd_node.context.ref.env.ref
    workflow_var_scope = github_context.job_context.ref.workflow_context.ref.workflow_variables.ref

    for loc, vals in bash_cmd_node.before_state.state.items():
        if evaluation.scope_matches(env_scope, loc.scope):
            for val in vals:
                visitor = FindSecretsVisitor(workflow_var_scope)
                visitor.visit_value(val)
                result.update(visitor.secrets)

    return result


def get_containing_github_job(
    node: core.Node, parents: dict[core.Node, core.Node]
) -> github.GitHubActionsNormalJobNode | None:
    """Return the GitHub job node containing the given node, if any.

    Parameters
    ----------
    node: core.Node
        The target node.
    parents: dict[core.Node, code.Node]
        The mapping of nodes to their parent nodes.

    Returns
    -------
    github.GitHubActionsNormalJobNode | None
        The containing job node, or None if there is no containing job.
    """
    caller_node: core.Node | None = parents.get(node)
    while caller_node is not None:
        match caller_node:
            case github.GitHubActionsWorkflowNode():
                break
            case github.GitHubActionsNormalJobNode():
                return caller_node

        caller_node = parents.get(caller_node)

    return None


def get_containing_github_step(
    node: core.Node, parents: dict[core.Node, core.Node]
) -> github.GitHubActionsRunStepNode | None:
    """Return the GitHub step node containing the given node, if any.

    Parameters
    ----------
    node: core.Node
        The target node.
    parents: dict[core.Node, code.Node]
        The mapping of nodes to their parent nodes.

    Returns
    -------
    github.GitHubActionsRunStepNode | None
        The containing step node, or None if there is no containing step.
    """
    caller_node: core.Node | None = parents.get(node)
    while caller_node is not None:
        match caller_node:
            case github.GitHubActionsWorkflowNode():
                break
            case github.GitHubActionsNormalJobNode():
                break
            case github.GitHubActionsRunStepNode():
                return caller_node

        caller_node = parents.get(caller_node)

    return None


def get_containing_github_workflow(
    node: core.Node, parents: dict[core.Node, core.Node]
) -> github.GitHubActionsWorkflowNode | None:
    """Return the GitHub workflow node containing the given node, if any.

    Parameters
    ----------
    node: core.Node
        The target node.
    parents: dict[core.Node, code.Node]
        The mapping of nodes to their parent nodes.

    Returns
    -------
    github.GitHubActionsWorkflowNode | None
        The containing workflow node, or None if there is no containing workflow.
    """
    caller_node: core.Node | None = parents.get(node)
    while caller_node is not None:
        match caller_node:
            case github.GitHubActionsWorkflowNode():
                return caller_node

        caller_node = parents.get(caller_node)

    return None


def _get_build_tool_commands(nodes: core.NodeForest, build_tool: BaseBuildTool) -> Iterable[BuildToolCommand]:
    """Traverse the callgraph and find all the reachable build tool commands."""
    for root in nodes.root_nodes:
        for node in core.traverse_bfs(root):
            # We are just interested in nodes that have bash commands.
            if isinstance(node, bash.BashSingleCommandNode):
                # We collect useful contextual information for the called BashNode.
                # The GitHub Actions workflow that triggers the path in the callgraph.
                workflow_node = None
                # The step in GitHub Actions job that triggers the path in the callgraph.
                step_node = None

                # Walk up the callgraph to find the relevant caller nodes.
                # In GitHub Actions a `GitHubWorkflowNode` may call several `GitHubJobNode`s
                # and a `GitHubJobNode` may call several steps, which can be external `GitHubWorkflowNode`
                # or inlined run nodes.
                # TODO: revisit this implementation if analysis of external workflows is supported in
                # the future, and decide if setting the caller workflow and job nodes to the nodes in the
                # main triggering workflow is still expected.
                workflow_node = get_containing_github_workflow(node, nodes.parents)
                step_node = get_containing_github_step(node, nodes.parents)

                # Find the bash commands that call the build tool.
                resolved_cmds = evaluation.evaluate(node, node.cmd)
                resolved_args = [evaluation.evaluate(node, arg) if arg is not None else None for arg in node.args]

                # TODO combinations

                cmd = [evaluation.get_single_resolved_str_with_default(resolved_cmds, "$MACARON_UNKNOWN")] + [
                    (
                        evaluation.get_single_resolved_str_with_default(resolved_arg, "$MACARON_UNKNOWN")
                        if resolved_arg is not None
                        else "$MACARON_UNKNOWN"
                    )
                    for resolved_arg in resolved_args
                ]

                if build_tool.is_build_command(cmd):
                    lang_versions = lang_distributions = lang_url = None
                    evaluated_installed_languages = evaluation.evaluate(
                        node,
                        facts.Read(
                            facts.Location(
                                node.context.ref.filesystem.ref,
                                facts.Installed(facts.StringLiteral(build_tool.language)),
                            )
                        ),
                    )
                    evaluated_installed_languages = evaluation.filter_symbolic_values(evaluated_installed_languages)

                    lang_versions = []
                    lang_distributions = []
                    lang_urls = []

                    for evaluated_installed_language in evaluated_installed_languages:
                        if isinstance(evaluated_installed_language[0], facts.InstalledPackage):
                            if isinstance(evaluated_installed_language[0].version, facts.StringLiteral):
                                lang_version_str = evaluated_installed_language[0].version.literal
                                if lang_version_str not in lang_versions:
                                    lang_versions.append(lang_version_str)
                            if isinstance(evaluated_installed_language[0].distribution, facts.StringLiteral):
                                lang_distribution_str = evaluated_installed_language[0].distribution.literal
                                if lang_distribution_str not in lang_distributions:
                                    lang_distributions.append(lang_distribution_str)
                            if isinstance(evaluated_installed_language[0].url, facts.StringLiteral):
                                lang_url_str = evaluated_installed_language[0].url.literal
                                if lang_url_str not in lang_urls:
                                    lang_urls.append(lang_url_str)

                    lang_url = lang_urls[0] if len(lang_urls) > 0 else ""

                    lang_versions = sorted(lang_versions)
                    lang_distributions = sorted(lang_distributions)
                    lang_urls = sorted(lang_urls)

                    yield BuildToolCommand(
                        ci_path=(
                            workflow_node.context.ref.source_filepath
                            if workflow_node is not None
                            else node.context.ref.source_filepath
                        ),
                        command=cmd,
                        step_node=step_node,
                        language=build_tool.language,
                        language_versions=lang_versions,
                        language_distributions=lang_distributions,
                        language_url=lang_url,
                        reachable_secrets=list(get_reachable_secrets(node)),
                        events=get_ci_events_from_workflow(workflow_node.definition) if workflow_node else [],
                    )


def get_build_tool_commands(nodes: core.NodeForest, build_tool: BaseBuildTool) -> Iterable[BuildToolCommand]:
    """Traverse the callgraph and find all the reachable build tool commands.

    This generator yields sorted build tool command objects to allow a deterministic behavior.
    The objects are sorted based on the string representation of the build tool object.

    Parameters
    ----------
    nodes: core.NodeForest
        The callgraph reachable from the CI workflows.
    build_tool: BaseBuildTool
        The corresponding build tool for which shell commands need to be detected.

    Yields
    ------
    BuildToolCommand
        The object that contains the build command as well useful contextual information.
    """
    return sorted(_get_build_tool_commands(nodes, build_tool), key=str)


def get_ci_events_from_workflow(workflow: github_workflow_model.Workflow) -> list[str]:
    """Get the CI events that trigger the GitHub Action workflow.

    Parameters
    ----------
    workflow: github_workflow_model.Workflow
        The target GitHub Action workflow.

    Returns
    -------
    list[str]
        The list of event names.
    """
    result: list[str] = []
    on = workflow["on"]
    if isinstance(on, str):
        result.append(on)
    elif isinstance(on, list):
        for hook in on:
            result.append(hook)
    else:
        for key in on:
            result.append(key)

    return result
