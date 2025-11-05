# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Dataflow analysis implementation for analysing Bash shell scripts."""

from __future__ import annotations

import json
import os.path
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from itertools import product
from typing import cast

from macaron import MACARON_PATH
from macaron.code_analyzer.dataflow_analysis import core, evaluation, facts, github, models, printing
from macaron.errors import CallGraphError, ParseError
from macaron.parsers import bashparser, bashparser_model


class BashExit(core.ExitType):
    """Exit type for Bash exit statement."""

    def __hash__(self) -> int:
        return 37199

    def __eq__(self, other: object) -> bool:
        return isinstance(other, BashExit)


# Convenience instance of BashExit.
BASH_EXIT = BashExit()


class BashReturn(core.ExitType):
    """Exit type for returning from a Bash function."""

    def __hash__(self) -> int:
        return 91193

    def __eq__(self, other: object) -> bool:
        return isinstance(other, BashReturn)


# Convenience instance of BashReturn.
BASH_RETURN = BashReturn()


@dataclass(frozen=True)
class BashScriptContext(core.Context):
    """Context for a Bash script."""

    #: Outer context, which may be a GitHub run step, another Bash script
    #: that ran this script, or just the outermost analysis context if analysing
    #: the script in isolation.
    outer_context: (
        core.ContextRef[github.GitHubActionsStepContext]
        | core.ContextRef[BashScriptContext]
        | core.ContextRef[core.AnalysisContext]
    )
    #: Scope for filesystem used by the script.
    filesystem: core.ContextRef[facts.Scope]
    #: Scope for env variables within the script.
    env: core.ContextRef[facts.Scope]
    #: Scope for defined functions within the script.
    func_decls: core.ContextRef[facts.Scope]
    #: Scope for the stdin attached to the Bash process.
    stdin_scope: core.ContextRef[facts.Scope]
    #: Location for the stdin attached to the Bash process.
    stdin_loc: facts.LocationSpecifier
    #: Scope for the stdout attached to the Bash process.
    stdout_scope: core.ContextRef[facts.Scope]
    #: Location for the stdout attached to the Bash process.
    stdout_loc: facts.LocationSpecifier
    #: Filepath for Bash script file.
    source_filepath: str

    @staticmethod
    def create_from_run_step(
        context: core.ContextRef[github.GitHubActionsStepContext], source_filepath: str
    ) -> BashScriptContext:
        """Create a new Bash script context (for being called from a GitHub step) and its associated scopes.

        Reuses the filesystem and stdout scopes from the outer context, env scope inherits from the outer scope.

        Parameters
        ----------
        context: core.ContextRef[github.GitHubActionsStepContext]
            Outer step context.
        source_filepath: str
            Filepath of Bash script file.

        Returns
        -------
        BashScriptContext
            The new Bash script context.
        """
        return BashScriptContext(
            context.get_non_owned(),
            context.ref.job_context.ref.filesystem.get_non_owned(),
            core.OwningContextRef(facts.Scope("env", context.ref.env.ref)),
            core.OwningContextRef(facts.Scope("func_decls")),
            stdin_scope=core.OwningContextRef(facts.Scope("stdin")),
            stdin_loc=facts.Console(),
            stdout_scope=context.ref.job_context.ref.workflow_context.ref.console.get_non_owned(),
            stdout_loc=facts.Console(),
            source_filepath=source_filepath,
        )

    @staticmethod
    def create_from_bash_script(context: core.ContextRef[BashScriptContext], source_filepath: str) -> BashScriptContext:
        """Create a new Bash script context (for being called from another Bash script) and its associated scopes.

        Reuses the filesystem, stdin, and stdout scopes from the outer context, env scope inherits from the outer context.

        Parameters
        ----------
        context: core.ContextRef[BashScriptContext]
            Outer Bash script context.
        source_filepath: str
            Filepath of Bash script file.

        Returns
        -------
        BashScriptContext
            The new Bash script context.
        """
        return BashScriptContext(
            context.get_non_owned(),
            context.ref.filesystem.get_non_owned(),
            core.OwningContextRef(facts.Scope("env", context.ref.env.ref)),
            core.OwningContextRef(facts.Scope("func_decls")),
            stdin_scope=context.ref.stdin_scope.get_non_owned(),
            stdin_loc=facts.Console(),
            stdout_scope=context.ref.stdout_scope.get_non_owned(),
            stdout_loc=facts.Console(),
            source_filepath=source_filepath,
        )

    @staticmethod
    def create_in_isolation(context: core.ContextRef[core.AnalysisContext], source_filepath: str) -> BashScriptContext:
        """Create a new Bash script context (for being analysed in isolation) and its associated scopes.

        Parameters
        ----------
        context: core.ContextRef[core.AnalysisContext]
            Outer analysis context.
        source_filepath: str
            Filepath of Bash script file.

        Returns
        -------
        BashScriptContext
            The new Bash script context.
        """
        return BashScriptContext(
            context.get_non_owned(),
            core.OwningContextRef(facts.Scope("filesystem")),
            core.OwningContextRef(facts.Scope("env")),
            core.OwningContextRef(facts.Scope("func_decls")),
            stdin_scope=core.OwningContextRef(facts.Scope("stdin")),
            stdin_loc=facts.Console(),
            stdout_scope=core.OwningContextRef(facts.Scope("stdout")),
            stdout_loc=facts.Console(),
            source_filepath=source_filepath,
        )

    def with_stdin(
        self, stdin_scope: core.ContextRef[facts.Scope], stdin_loc: facts.LocationSpecifier
    ) -> BashScriptContext:
        """Return a modified bash script context with the given stdin."""
        return BashScriptContext(
            self.outer_context,
            self.filesystem,
            self.env,
            self.func_decls,
            stdin_scope,
            stdin_loc,
            self.stdout_scope,
            self.stdout_loc,
            self.source_filepath,
        )

    def with_stdout(
        self, stdout_scope: core.ContextRef[facts.Scope], stdout_loc: facts.LocationSpecifier
    ) -> BashScriptContext:
        """Return a modified bash script context with the given stdout."""
        return BashScriptContext(
            self.outer_context,
            self.filesystem,
            self.env,
            self.func_decls,
            self.stdin_scope,
            self.stdin_loc,
            stdout_scope,
            stdout_loc,
            self.source_filepath,
        )

    def get_containing_github_context(self) -> github.GitHubActionsStepContext | None:
        """Return the (possibly transitive) containing GitHub step context, if there is one."""
        outer_context = self.outer_context.ref
        while isinstance(outer_context, BashScriptContext):
            outer_context = outer_context.outer_context.ref

        if isinstance(outer_context, github.GitHubActionsStepContext):
            return outer_context
        return None

    def get_containing_analysis_context(self) -> core.AnalysisContext:
        """Return the (possibly transitive) containing analysis context."""
        outer_context = self.outer_context.ref
        while isinstance(outer_context, BashScriptContext):
            outer_context = outer_context.outer_context.ref

        if isinstance(outer_context, github.GitHubActionsStepContext):
            return outer_context.job_context.ref.workflow_context.ref.analysis_context.ref

        return outer_context

    def direct_refs(self) -> Iterator[core.ContextRef[core.Context] | core.ContextRef[facts.Scope]]:
        """Yield the direct references of the context, either to scopes or to other contexts."""
        yield self.outer_context
        yield self.filesystem
        yield self.env
        yield self.func_decls
        yield self.stdin_scope
        yield self.stdout_scope


class RawBashScriptNode(core.InterpretationNode):
    """Interpretation node representing a Bash script (with the script as an unparsed string value).

    Defines how to resolve and parse the Bash script content and generate the analysis representation.
    """

    #: Value for Bash script content (as a string).
    script: facts.Value
    #: Bash script context.
    context: core.ContextRef[BashScriptContext]

    def __init__(self, script: facts.Value, context: core.ContextRef[BashScriptContext]) -> None:
        """Initialize Bash script node.

        Parameters
        ----------
        script: facts.Value
            Value for Bash script content (as a string).
        context: core.ContextRef[BashScriptContext]
            Bash script context.
        """
        super().__init__()
        self.script = script
        self.context = context

    def identify_interpretations(self, state: core.State) -> dict[core.InterpretationKey, Callable[[], core.Node]]:
        """Interpret the Bash script to resolve and parse the Bash script content and generate the analysis representation."""
        if isinstance(self.script, facts.StringLiteral):
            script_str = self.script.literal

            def build_bash_script() -> core.Node:
                try:
                    parsed_bash = bashparser.parse_raw(script_str, MACARON_PATH)
                    return BashScriptNode.create(parsed_bash, self.context.get_non_owned())
                except ParseError:
                    return core.NoOpStatementNode()

            return {"default": build_bash_script}

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


class BashScriptNode(core.ControlFlowGraphNode):
    """Control-flow-graph node representing a Bash script.

    Control flow structure consists of a sequence of Bash statements.
    Note that this can model complex control flow with branching, loops, etc.
    because those control flow constructs will be statement nodes with their
    own control flow nested within.

    Control flow that the cuts across multiple levels, such as an exit statement
    within a if statement branch that would cause the entire script to exit
    early, are modelled using the alternate exits mechanism (i.e. exit statement
    creates a BashExit exit state, in the enclosing control-flow constructs the
    successor of the BashExit exit of a child node will be an early BashExit exit
    of that construct, and so on up until this node, where there will be a early
    normal exit, and so the caller of this script would then proceed as normal after
    the script exits).
    """

    #: Parsed Bash script AST.
    definition: bashparser_model.File
    #: Statement nodes in execution order.
    stmts: list[BashStatementNode]
    #: Bash script context.
    context: core.ContextRef[BashScriptContext]
    #: Control flow graph.
    _cfg: core.ControlFlowGraph

    def __init__(
        self,
        definition: bashparser_model.File,
        stmts: list[BashStatementNode],
        context: core.ContextRef[BashScriptContext],
    ) -> None:
        """Initialize Bash script node.

        Typically, construction should be done via the create function rather than using this constructor directly.

        Parameters
        ----------
        definition: bashparser_model.File
            Parsed Bash script AST.
        stmts: list[BashStatementNode]
            Statement nodes in execution order.
        context: core.ContextRef[BashScriptContext]
            Bash script context.
        """
        super().__init__()
        self.definition = definition
        self.stmts = stmts
        self.context = context

        self._cfg = core.ControlFlowGraph.create_from_sequence(self.stmts)

    def children(self) -> Iterator[core.Node]:
        """Yield the nodes in the sequence."""
        yield from self.stmts

    def get_entry(self) -> core.Node:
        """Return the entry node, the first statement in the sequence."""
        return self._cfg.get_entry()

    def get_successors(self, node: core.Node, exit_type: core.ExitType) -> set[core.Node | core.ExitType]:
        """Return the successor for a given node.

        Returns the next in the sequence or the exit in the case of the last node, or an
        early exit in the case of a BashExit or BashReturn exit type.
        """
        if isinstance(exit_type, (BashExit, BashReturn)):
            return {core.DEFAULT_EXIT}
        return self._cfg.get_successors(node, core.DEFAULT_EXIT)

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}

        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result

    @staticmethod
    def create(script: bashparser_model.File, context: core.NonOwningContextRef[BashScriptContext]) -> BashScriptNode:
        """Create Bash script node from Bash script AST.

        Parameters
        ----------
        script: bashparser_model.File
            Parsed Bash script AST.
        context: core.NonOwningContextRef[BashScriptContext]
            Bash script context.
        """
        stmts = [BashStatementNode(stmt, context) for stmt in script["Stmts"]]
        return BashScriptNode(script, stmts, context)


class BashBlockNode(core.ControlFlowGraphNode):
    """Control-flow-graph node representing a Bash block.

    Control flow structure consists of a sequence of Bash statements.
    """

    #: Parsed block AST or list of statement ASTs.
    definition: bashparser_model.Block | list[bashparser_model.Stmt]
    #: Statement nodes in execution order.
    stmts: list[BashStatementNode]
    #: Bash script context.
    context: core.ContextRef[BashScriptContext]
    #: Control flow graph.
    _cfg: core.ControlFlowGraph

    def __init__(
        self,
        definition: bashparser_model.Block | list[bashparser_model.Stmt],
        stmts: list[BashStatementNode],
        context: core.ContextRef[BashScriptContext],
    ) -> None:
        """Initialize Bash block node.

        Typically, construction should be done via the create function rather than using this constructor directly.

        Parameters
        ----------
        definition: bashparser_model.Block | list[bashparser_model.Stmt]
            Parsed block AST or list of statement ASTs.
        stmts: list[BashStatementNode]
            Statement nodes in execution order.
        context: core.ContextRef[BashScriptContext]
            Bash script context.
        """
        super().__init__()
        self.definition = definition
        self.stmts = stmts
        self.context = context

        self._cfg = core.ControlFlowGraph.create_from_sequence(self.stmts)

    def children(self) -> Iterator[core.Node]:
        """Yield the nodes in the sequence."""
        yield from self.stmts

    def get_entry(self) -> core.Node:
        """Return the entry node, the first statement in the sequence."""
        return self._cfg.get_entry()

    def get_successors(self, node: core.Node, exit_type: core.ExitType) -> set[core.Node | core.ExitType]:
        """Return the successor for a given node.

        Returns the next in the sequence or the exit in the case of the last node, or a
        propagated early exit of the same type in the case of a BashExit or BashReturn exit type.
        """
        if isinstance(exit_type, (BashExit, BashReturn)):
            return {exit_type}
        return self._cfg.get_successors(node, core.DEFAULT_EXIT)

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the line number and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        if isinstance(self.definition, list):
            if len(self.definition) > 0:
                result["line num (in script)"] = {(None, str(self.definition[0]["Pos"]["Line"]))}
        else:
            result["line num (in script)"] = {(None, str(self.definition["Pos"]["Line"]))}
        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result

    @staticmethod
    def create(
        script: bashparser_model.Block | list[bashparser_model.Stmt],
        context: core.NonOwningContextRef[BashScriptContext],
    ) -> BashBlockNode:
        """Create Bash block node from block AST or list of statement ASTs.

        Parameters
        ----------
        script: bashparser_model.Block | list[bashparser_model.Stmt]
            Parsed block AST or list of statement ASTs.
        context: core.NonOwningContextRef[BashScriptContext]
            Bash script context.
        """
        if isinstance(script, list):
            stmts = [BashStatementNode(stmt, context) for stmt in script]
        else:
            stmts = [BashStatementNode(stmt, context) for stmt in script["Stmts"]]
        return BashBlockNode(script, stmts, context)


class BashFuncCallNode(core.ControlFlowGraphNode):
    """Control-flow-graph node representing a call to a Bash function.

    Control flow structure consists of a single block containing the function body.
    """

    #: The parsed AST of the callsite statement.
    call_definition: bashparser_model.Stmt
    #: The parsed AST of the function declaration.
    func_definition: bashparser_model.FuncDecl
    #: Node representing the function body.
    block: BashBlockNode
    #: Bash script context.
    context: core.ContextRef[BashScriptContext]

    def __init__(
        self,
        call_definition: bashparser_model.Stmt,
        func_definition: bashparser_model.FuncDecl,
        block: BashBlockNode,
        context: core.ContextRef[BashScriptContext],
    ) -> None:
        """Initialize Bash function call node.

        Parameters
        ----------
        call_definition: bashparser_model.Stmt
            The parsed AST of the callsite statement.
        func_definition: bashparser_model.FuncDecl
            The parsed AST of the function declaration.
        block: BashBlockNode
            Node representing the function body.
        context: core.ContextRef[BashScriptContext]
            Bash script context.
        """
        super().__init__()
        self.call_definition = call_definition
        self.func_definition = func_definition
        self.block = block
        self.context = context

        self._cfg = core.ControlFlowGraph.create_from_sequence([self.block])

    def children(self) -> Iterator[core.Node]:
        """Yield the function body block node."""
        yield self.block

    def get_entry(self) -> core.Node:
        """Return the function body block node."""
        return self._cfg.get_entry()

    def get_successors(self, node: core.Node, exit_type: core.ExitType) -> set[core.Node | core.ExitType]:
        """Return the successor for a given node.

        Returns the next node in the sequence or the exit in the case of the last node, or an
        early exit in the case of a BashReturn exit type, or a propagated early BashExit exit
        in the case of a BashExit exit type.
        """
        if isinstance(exit_type, BashReturn):
            return {core.DEFAULT_EXIT}
        if isinstance(exit_type, BashExit):
            return {exit_type}
        return self._cfg.get_successors(node, core.DEFAULT_EXIT)

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table.

        Contains the line number of the callsite, the line number of the function declaration, and the scopes.
        """
        result: dict[str, set[tuple[str | None, str]]] = {}
        result["line num (in script)"] = {(None, str(self.call_definition["Pos"]["Line"]))}
        result["callee decl line num (in script)"] = {(None, str(self.func_definition["Pos"]["Line"]))}
        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result


def get_stdout_redirects(stmt: bashparser_model.Stmt, context: BashScriptContext) -> set[facts.Location]:
    """Extract the stdout redirects specified on the statement as a set of location expressions."""
    redirs: set[facts.Location] = set()
    for redir in stmt.get("Redirs", []):
        if redir["Op"] in {
            bashparser_model.RedirOperators.RdrOut.value,
            bashparser_model.RedirOperators.RdrAll.value,
            bashparser_model.RedirOperators.AppAll.value,
            bashparser_model.RedirOperators.AppOut.value,
        }:
            if "Word" in redir:
                redir_word = redir["Word"]
                redir_val = convert_shell_word_to_value(redir_word, context)
                if redir_val is not None:
                    redirs.add(facts.Location(context.filesystem.ref, facts.Filesystem(redir_val[0])))
    return redirs


class BashStatementNode(core.InterpretationNode):
    """Interpretation node representing any kind of Bash statement.

    Defines how to interpret the different kinds of statements and generate the appropriate
    analysis representation.
    """

    #: The parsed statement AST.
    definition: bashparser_model.Stmt
    #: Bash script context.
    context: core.ContextRef[BashScriptContext]

    def __init__(self, definition: bashparser_model.Stmt, context: core.ContextRef[BashScriptContext]) -> None:
        """Initialize statement node."""
        super().__init__()
        self.definition = definition
        self.context = context

    def identify_interpretations(self, state: core.State) -> dict[core.InterpretationKey, Callable[[], core.Node]]:
        """Interpret the different kinds of statements and generate the appropriate analysis representation."""
        cmd = self.definition["Cmd"]
        if (
            bashparser_model.is_call_expr(cmd)
            and len(cmd.get("Args", [])) == 0
            and "Assigns" in cmd
            and len(cmd["Assigns"]) == 1
        ):
            # Single variable assignment statement.
            assign = cmd["Assigns"][0]

            def build_assign() -> core.Node:
                rhs_content = (
                    parse_content(assign["Value"]["Parts"], True)
                    if "Value" in assign
                    else [LiteralOrEnvVar(is_env_var=False, literal="")]
                )
                if rhs_content is not None:
                    rhs_val = convert_shell_value_sequence_to_fact_value(rhs_content, self.context.ref)
                    return models.VarAssignNode(
                        kind=models.VarAssignKind.BASH_ENV_VAR,
                        var_scope=self.context.ref.env.ref,
                        var_name=facts.StringLiteral(assign["Name"]["Value"]),
                        value=rhs_val,
                    )
                return core.NoOpStatementNode()

            return {"default": build_assign}
        if bashparser_model.is_call_expr(cmd) and "Args" in cmd and len(cmd["Args"]) > 0:
            # Statement executing a command, generate node with command name expression and
            # expressions for each argument value.
            # In the case where a word may tokenize as multiple words depending on the value,
            # attempt to resolve them and where they do resolve to something that tokenizes as
            # multiple args, generate alternative interpretations with those expanded number of
            # args, alongside interpretations where those words are a dynamic expression that is
            # constrained to be a single word.
            arg_vals = [convert_shell_word_to_value(arg, self.context.ref) for arg in cmd["Args"]]
            multitoken_resolved_arg_vals: dict[
                int, list[tuple[list[bashparser_model.Word], evaluation.ReadBindings]]
            ] = defaultdict(list)

            for index, arg_val_elem in enumerate(arg_vals):
                if arg_val_elem is None:
                    continue
                arg_val_elem_val, arg_quoted = arg_val_elem
                if not arg_quoted:
                    resolved_arg_vals = evaluation.evaluate(self, arg_val_elem_val)
                    for resolved_arg_val, resolved_arg_val_bindings in resolved_arg_vals:
                        match resolved_arg_val:
                            case facts.StringLiteral(literal):
                                parsed_bash_expr = parse_bash_expr(literal)
                                if parsed_bash_expr is not None and len(parsed_bash_expr) > 1:
                                    multitoken_resolved_arg_vals[index].append(
                                        (parsed_bash_expr, resolved_arg_val_bindings)
                                    )
            arg_indices_in_order: list[int] = []
            values_indices_in_order: list[list[int]] = []
            for index, vals in multitoken_resolved_arg_vals.items():
                arg_indices_in_order.append(index)
                values_indices_in_order.append([index for index, _ in enumerate(vals)] + [-1])

            # Cross product could become very expensive
            values_product = list(product(*values_indices_in_order))

            if len(values_product) == 0:
                values_product = [()]

            result: dict[core.InterpretationKey, Callable[[], core.Node]] = {}

            for values_product_elem in values_product:
                new_arg_vals: dict[int, list[facts.Value | None]] = {}
                read_bindings_list: list[evaluation.ReadBindings] = []
                for arg_index, value_index in zip(arg_indices_in_order, values_product_elem):
                    if value_index != -1:
                        expanded_vals, bindings = multitoken_resolved_arg_vals[arg_index][value_index]
                        read_bindings_list.append(bindings)
                        converted = [
                            convert_shell_word_to_value(expanded_val, self.context.ref)
                            for expanded_val in expanded_vals
                        ]
                        new_arg_vals[arg_index] = [x[0] if x is not None else None for x in converted]
                    else:
                        old_arg_val = arg_vals[arg_index]
                        new_arg_vals[arg_index] = [
                            facts.SingleBashTokenConstraint(old_arg_val[0]) if old_arg_val is not None else None
                        ]

                combined_bindings = evaluation.ReadBindings.combine_bindings(read_bindings_list)
                if combined_bindings is None:
                    continue
                full_arg_list: list[facts.Value | None] = []

                for index, arg_val in enumerate(arg_vals):
                    if index in new_arg_vals:
                        full_arg_list.extend(new_arg_vals[index])
                    else:
                        full_arg_list.append(arg_val[0] if arg_val is not None else None)

                cmd_arg = full_arg_list[0]
                # TODO subshells
                if cmd_arg is not None:
                    cmd_arg_val = cmd_arg

                    def build_single_cmd(  # pylint: disable=dangerous-default-value
                        cmd_arg: facts.Value = cmd_arg_val, cmd_arg_list: list[facts.Value | None] = full_arg_list[1:]
                    ) -> core.Node:
                        stdout_redirs = get_stdout_redirects(self.definition, self.context.ref)
                        return BashSingleCommandNode(
                            self.definition, self.context.get_non_owned(), cmd_arg, cmd_arg_list, stdout_redirs
                        )

                    result[("cmd", values_product_elem, combined_bindings)] = build_single_cmd
            return result
        if bashparser_model.is_if_clause(cmd):
            # If statement.

            def build_if() -> core.Node:
                return BashIfClauseNode.create(cmd, self.context.get_non_owned())

            return {"default": build_if}

        if bashparser_model.is_for_clause(cmd):
            # For statement.

            def build_for() -> core.Node:
                return BashForClauseNode.create(cmd, self.context.get_non_owned())

            return {"default": build_for}
        if bashparser_model.is_binary_cmd(cmd):
            match cmd["Op"]:
                case bashparser_model.BinCmdOperators.Pipe.value:

                    def build_pipe() -> core.Node:
                        return BashPipeNode.create(cmd, self.context.get_non_owned())

                    return {"default": build_pipe}
                case bashparser_model.BinCmdOperators.PipeAll.value:
                    pass
                case bashparser_model.BinCmdOperators.AndStmt.value:

                    def build_and() -> core.Node:
                        return BashAndNode.create(cmd, self.context.get_non_owned())

                    return {"default": build_and}
                case bashparser_model.BinCmdOperators.OrStmt.value:

                    def build_or() -> core.Node:
                        return BashOrNode.create(cmd, self.context.get_non_owned())

                    return {"default": build_or}
            raise CallGraphError("unknown binary operator: " + str(cmd["Op"]))
        if bashparser_model.is_func_decl(cmd):
            # Represent Bash function decl as a store of the serialized function defintion,
            # into a variable in the function decl scope.
            func_decl_str = json.dumps(cmd)

            def build_func_decl() -> core.Node:
                return models.VarAssignNode(
                    kind=models.VarAssignKind.BASH_FUNC_DECL,
                    var_scope=self.context.ref.func_decls.ref,
                    var_name=facts.StringLiteral(cmd["Name"]["Value"]),
                    value=facts.StringLiteral(func_decl_str),
                )

            return {"default": build_func_decl}
        if bashparser_model.is_block(cmd):

            def build_block() -> core.Node:
                return BashBlockNode.create(cmd, self.context.get_non_owned())

            return {"default": build_block}

        def build_noop() -> core.Node:
            return core.NoOpStatementNode()

        return {"default": build_noop}

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the line number and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        result["line num (in script)"] = {(None, str(self.definition["Pos"]["Line"]))}
        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result


class BashIfClauseNode(core.ControlFlowGraphNode):
    """Control-flow-graph node representing a Bash if statement.

    Control flow structure consists of executing the statements of the condition,
    followed by a branch to execute either the then node or the else node (or if
    there is no else node, exit immediately). The analysis is not path sensitive,
    so both branches are always considered possible regardless of the condition.
    """

    #: Parsed if statement AST.
    definition: bashparser_model.IfClause
    #: Block node to execute the condition.
    cond_stmts: BashBlockNode
    #: Block node for the case where the condition is true.
    then_stmts: BashBlockNode
    #: Node for the case where the condition is false, if any
    #: (will be another if node in the case of an elif).
    else_stmts: BashBlockNode | BashIfClauseNode | None
    #: Bash script context.
    context: core.ContextRef[BashScriptContext]
    #: Control flow graph.
    _cfg: core.ControlFlowGraph

    def __init__(
        self,
        definition: bashparser_model.IfClause,
        cond_stmts: BashBlockNode,
        then_stmts: BashBlockNode,
        else_stmts: BashBlockNode | BashIfClauseNode | None,
        context: core.ContextRef[BashScriptContext],
    ) -> None:
        """Initialize Bash if statement node.

        Typically, construction should be done via the create function rather than using this constructor directly.

        Parameters
        ----------
        definition: bashparser_model.IfClause
            Parsed if statement AST.
        cond_stmts: BashBlockNode
            Block node to execute the condition.
        then_stmts: BashBlockNode
            Block node for the case where the condition is true.
        else_stmts: BashBlockNode | BashIfClauseNode | None
            Node for the case where the condition is false, if any
            (will be another if node in the case of an elif).
        context: core.ContextRef[BashScriptContext]
            Bash script context.
        """
        super().__init__()
        self.definition = definition
        self.cond_stmts = cond_stmts
        self.then_stmts = then_stmts
        self.else_stmts = else_stmts
        self.context = context

        self._cfg = core.ControlFlowGraph(self.cond_stmts)
        self._cfg.add_successor(self.cond_stmts, core.DEFAULT_EXIT, self.then_stmts)
        self._cfg.add_successor(self.then_stmts, core.DEFAULT_EXIT, core.DEFAULT_EXIT)
        if else_stmts is not None:
            self._cfg.add_successor(self.cond_stmts, core.DEFAULT_EXIT, else_stmts)
            self._cfg.add_successor(else_stmts, core.DEFAULT_EXIT, core.DEFAULT_EXIT)
        else:
            self._cfg.add_successor(self.cond_stmts, core.DEFAULT_EXIT, core.DEFAULT_EXIT)

    def children(self) -> Iterator[core.Node]:
        """Yield the condition node, then node and (if present) else node."""
        yield self.cond_stmts
        yield self.then_stmts
        if self.else_stmts is not None:
            yield self.else_stmts

    def get_entry(self) -> core.Node:
        """Return the entry node (the condition node)."""
        return self._cfg.get_entry()

    def get_successors(self, node: core.Node, exit_type: core.ExitType) -> set[core.Node | core.ExitType]:
        """Return the successor for a given node.

        Returns a propagated early exit of the same type in the case of a BashExit or BashReturn exit type.
        """
        if isinstance(exit_type, (BashExit, BashReturn)):
            return {exit_type}
        return self._cfg.get_successors(node, core.DEFAULT_EXIT)

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the line number and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        result["line num (in script)"] = {(None, str(self.definition["Pos"]["Line"]))}
        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result

    @staticmethod
    def create(
        if_stmt: bashparser_model.IfClause, context: core.NonOwningContextRef[BashScriptContext]
    ) -> BashIfClauseNode:
        """Create a Bash if statement node from if statement AST.

        Parameters
        ----------
        if_stmt: bashparser_model.IfClause
            Parsed if statement AST.
        context: core.NonOwningContextRef[BashScriptContext]
            Bash script context.
        """
        cond_stmts = BashBlockNode.create(if_stmt["Cond"], context)
        then_stmts = BashBlockNode.create(if_stmt["Then"], context)
        else_clause = if_stmt.get("Else")
        else_part: BashBlockNode | BashIfClauseNode | None = None
        if else_clause is None:
            else_part = None
        elif bashparser_model.is_else_clause(else_clause):
            else_part = BashBlockNode.create(else_clause["Then"], context)
        else:
            else_part = BashIfClauseNode.create(cast(bashparser_model.IfClause, else_clause), context)
        return BashIfClauseNode(
            definition=if_stmt, cond_stmts=cond_stmts, then_stmts=then_stmts, else_stmts=else_part, context=context
        )


class BashForClauseNode(core.ControlFlowGraphNode):
    """Control-flow-graph node representing a Bash for statement.

    Control flow structure consists of executing the statements of the condition,
    followed by a branch to execute or skip the loop body node . The analysis is
    not path sensitive, so both branches are always considered possible regardless
    of the condition.

    TODO: Currently doesn't actually model the loop back edge (need more testing to
    be confident of analysis termination in the presence of loops).
    """

    #: Parsed for statement AST.
    definition: bashparser_model.ForClause
    #: Block node to execute the initializer.
    init_stmts: BashBlockNode | None
    #: Block node to execute the condition.
    cond_stmts: BashBlockNode | None
    #: Block node for the loop body.
    body_stmts: BashBlockNode
    #: Block node to execute the post.
    post_stmts: BashBlockNode | None
    #: Bash script context.
    context: core.ContextRef[BashScriptContext]
    #: Control flow graph.
    _cfg: core.ControlFlowGraph

    def __init__(
        self,
        definition: bashparser_model.ForClause,
        init_stmts: BashBlockNode | None,
        cond_stmts: BashBlockNode | None,
        body_stmts: BashBlockNode,
        post_stmts: BashBlockNode | None,
        context: core.ContextRef[BashScriptContext],
    ) -> None:
        """Initialize Bash for statement node.

        Typically, construction should be done via the create function rather than using this constructor directly.

        Parameters
        ----------
        definition: bashparser_model.ForClause
            Parsed if statement AST.
        init_stmts: BashBlockNode | None
            Block node to execute the initializer.
        cond_stmts: BashBlockNode | None
            Block node to execute the condition.
        body_stmts: BashBlockNode
            Block node for the body.
        post_stmts: BashBlockNode | None
            Block node to execute the post.
        context: core.ContextRef[BashScriptContext]
            Bash script context.
        """
        super().__init__()
        self.definition = definition
        self.init_stmts = init_stmts
        self.cond_stmts = cond_stmts
        self.body_stmts = body_stmts
        self.post_stmts = post_stmts
        self.context = context

        self._cfg = core.ControlFlowGraph.create_from_sequence(
            list(filter(core.node_is_not_none, [self.init_stmts, self.cond_stmts, self.body_stmts, self.post_stmts]))
        )

    def children(self) -> Iterator[core.Node]:
        """Yield the initializer, condition, body and post nodes."""
        if self.init_stmts is not None:
            yield self.init_stmts
        if self.cond_stmts is not None:
            yield self.cond_stmts
        yield self.body_stmts
        if self.post_stmts is not None:
            yield self.post_stmts

    def get_entry(self) -> core.Node:
        """Return the entry node."""
        return self._cfg.get_entry()

    def get_successors(self, node: core.Node, exit_type: core.ExitType) -> set[core.Node | core.ExitType]:
        """Return the successor for a given node.

        Returns a propagated early exit of the same type in the case of a BashExit or BashReturn exit type.
        """
        if isinstance(exit_type, (BashExit, BashReturn)):
            return {exit_type}
        return self._cfg.get_successors(node, core.DEFAULT_EXIT)

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the line number and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        result["line num (in script)"] = {(None, str(self.definition["Pos"]["Line"]))}
        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result

    @staticmethod
    def create(
        for_stmt: bashparser_model.ForClause, context: core.NonOwningContextRef[BashScriptContext]
    ) -> BashForClauseNode:
        """Create a Bash for statement node from for statement AST.

        Parameters
        ----------
        for_stmt: bashparser_model.ForClause
            Parsed for statement AST.
        context: core.NonOwningContextRef[BashScriptContext]
            Bash script context.
        """
        body_stmts = BashBlockNode.create(for_stmt["Do"], context)

        loop = for_stmt["Loop"]
        if not bashparser_model.is_cstyle_loop(loop):
            return BashForClauseNode(
                definition=for_stmt,
                init_stmts=None,
                cond_stmts=None,
                body_stmts=body_stmts,
                post_stmts=None,
                context=context,
            )

        init_stmts: BashBlockNode | None = None
        if "Init" in loop:
            init_arithm_cmd = bashparser_model.ArithmCmd(
                Type="ArithmCmd",
                Pos=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                End=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                Left=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                Right=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                X=loop["Init"],
            )
            init_stmt = bashparser_model.Stmt(
                Cmd=init_arithm_cmd,
                Pos=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                End=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                Position=bashparser_model.Pos(Offset=0, Line=0, Col=0),
            )
            init_stmts = BashBlockNode.create([init_stmt], context)

        cond_stmts: BashBlockNode | None = None
        if "Cond" in loop:
            cond_arithm_cmd = bashparser_model.ArithmCmd(
                Type="ArithmCmd",
                Pos=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                End=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                Left=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                Right=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                X=loop["Cond"],
            )
            cond_stmt = bashparser_model.Stmt(
                Cmd=cond_arithm_cmd,
                Pos=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                End=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                Position=bashparser_model.Pos(Offset=0, Line=0, Col=0),
            )
            cond_stmts = BashBlockNode.create([cond_stmt], context)

        post_stmts: BashBlockNode | None = None
        if "Post" in loop:
            post_arithm_cmd = bashparser_model.ArithmCmd(
                Type="ArithmCmd",
                Pos=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                End=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                Left=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                Right=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                X=loop["Post"],
            )
            post_stmt = bashparser_model.Stmt(
                Cmd=post_arithm_cmd,
                Pos=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                End=bashparser_model.Pos(Offset=0, Line=0, Col=0),
                Position=bashparser_model.Pos(Offset=0, Line=0, Col=0),
            )
            post_stmts = BashBlockNode.create([post_stmt], context)

        return BashForClauseNode(
            definition=for_stmt,
            init_stmts=init_stmts,
            cond_stmts=cond_stmts,
            body_stmts=body_stmts,
            post_stmts=post_stmts,
            context=context,
        )


@dataclass(frozen=True)
class BashPipeContext(core.Context):
    """Context for a Bash pipe operation.

    Introduces a scope and location to represent the pipe itself connecting the piped commands,
    where output from the piped-from command is written prior to being read as input by the piped-to
    command.
    """

    #: Outer Bash script context
    bash_script_context: core.ContextRef[BashScriptContext]
    #: Scope for pipe.
    pipe_scope: core.ContextRef[facts.Scope]
    #: Location for pipe.
    pipe_loc: facts.LocationSpecifier

    @staticmethod
    def create(context: core.ContextRef[BashScriptContext]) -> BashPipeContext:
        """Create a new pipe context and its associated scope."""
        return BashPipeContext(context.get_non_owned(), core.OwningContextRef(facts.Scope("pipe")), facts.Console())

    def direct_refs(self) -> Iterator[core.ContextRef[core.Context] | core.ContextRef[facts.Scope]]:
        """Yield the direct references of the context, either to scopes or to other contexts."""
        yield self.bash_script_context
        yield self.pipe_scope


class BashPipeNode(core.ControlFlowGraphNode):
    """Control flow node representing a Bash pipe ("|") binary command.

    Control flow structure consists of executing the left-hand side,
    followed by the right-hand side.
    A pipe scope and location is introduced to model the piping of the
    output from the first command to the input of the second command.
    """

    #: Parsed pipe binary command AST.
    definition: bashparser_model.BinaryCmd
    #: Left-hand side (first) command.
    lhs: BashStatementNode
    #: Right-hand side (second) command.
    rhs: BashStatementNode
    #: Pipe context.
    context: core.ContextRef[BashPipeContext]
    #: Control flow graph.
    _cfg: core.ControlFlowGraph

    def __init__(
        self,
        definition: bashparser_model.BinaryCmd,
        lhs: BashStatementNode,
        rhs: BashStatementNode,
        context: core.ContextRef[BashPipeContext],
    ) -> None:
        """Initialize Bash pipe node.

        Typically, construction should be done via the create function rather than using this constructor directly.

        Parameters
        ----------
        definition: bashparser_model.BinaryCmd
            Parsed pipe binary command AST.
        lhs: BashStatementNode
            Left-hand side (first) command.
        rhs: BashStatementNode
            Right-hand side (second) command.
        context: core.ContextRef[BashPipeContext]
            Pipe context.
        """
        super().__init__()
        self.definition = definition
        self.lhs = lhs
        self.rhs = rhs
        self.context = context

        self._cfg = core.ControlFlowGraph(self.lhs)
        self._cfg.add_successor(self.lhs, core.DEFAULT_EXIT, self.rhs)
        self._cfg.add_successor(self.rhs, core.DEFAULT_EXIT, core.DEFAULT_EXIT)

    def children(self) -> Iterator[core.Node]:
        """Yield the subcommands."""
        yield self.lhs
        yield self.rhs

    def get_entry(self) -> core.Node:
        """Return the entry node (the lhs node)."""
        return self._cfg.get_entry()

    def get_successors(self, node: core.Node, exit_type: core.ExitType) -> set[core.Node | core.ExitType]:
        """Return the successor for a given node.

        Returns a propagated early exit of the same type in the case of a BashExit or BashReturn exit type.
        """
        if isinstance(exit_type, (BashExit, BashReturn)):
            return {exit_type}
        return self._cfg.get_successors(node, core.DEFAULT_EXIT)

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the line number and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        result["line num (in script)"] = {(None, str(self.definition["Pos"]["Line"]))}
        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result

    @staticmethod
    def create(
        pipe_cmd: bashparser_model.BinaryCmd, context: core.NonOwningContextRef[BashScriptContext]
    ) -> BashPipeNode:
        """Create Bash pipe node from pipe binary command AST.

        Parameters
        ----------
        pipe_cmd: bashparser_model.BinaryCmd
            Parsed pipe binary command AST.
        context: core.NonOwningContextRef[BashScriptContext]
            Bash script context.
        """
        pipe_context = core.OwningContextRef(BashPipeContext.create(context))
        piped_from_context = core.NonOwningContextRef(
            context.ref.with_stdout(pipe_context.ref.pipe_scope.get_non_owned(), pipe_context.ref.pipe_loc)
        )
        piped_to_context = core.NonOwningContextRef(
            context.ref.with_stdin(pipe_context.ref.pipe_scope.get_non_owned(), pipe_context.ref.pipe_loc)
        )
        lhs = BashStatementNode(pipe_cmd["X"], piped_from_context)
        rhs = BashStatementNode(pipe_cmd["Y"], piped_to_context)
        return BashPipeNode(definition=pipe_cmd, lhs=lhs, rhs=rhs, context=pipe_context)


class BashAndNode(core.ControlFlowGraphNode):
    """Control flow node representing a Bash AND ("&&") binary command.

    Control flow structure consists of executing the left-hand side,
    followed by the right-hand side.

    (TODO model short circuit?)
    """

    #: Parsed AND binary command AST.
    definition: bashparser_model.BinaryCmd
    #: Left-hand side (first) command.
    lhs: BashStatementNode
    #: Right-hand side (second) command.
    rhs: BashStatementNode
    #: Bash script context.
    context: core.ContextRef[BashScriptContext]
    #: Control flow graph.
    _cfg: core.ControlFlowGraph

    def __init__(
        self,
        definition: bashparser_model.BinaryCmd,
        lhs: BashStatementNode,
        rhs: BashStatementNode,
        context: core.ContextRef[BashScriptContext],
    ) -> None:
        """Initialize Bash and node.

        Typically, construction should be done via the create function rather than using this constructor directly.

        Parameters
        ----------
        definition: bashparser_model.BinaryCmd
            Parsed AND binary command AST.
        lhs: BashStatementNode
            Left-hand side (first) command.
        rhs: BashStatementNode
            Right-hand side (second) command.
        context: core.ContextRef[BashScriptContext]
            Bash script context.
        """
        super().__init__()
        self.definition = definition
        self.lhs = lhs
        self.rhs = rhs
        self.context = context

        self._cfg = core.ControlFlowGraph.create_from_sequence([lhs, rhs])

    def children(self) -> Iterator[core.Node]:
        """Yield the subcommands."""
        yield self.lhs
        yield self.rhs

    def get_entry(self) -> core.Node:
        """Return the entry node (the lhs node)."""
        return self._cfg.get_entry()

    def get_successors(self, node: core.Node, exit_type: core.ExitType) -> set[core.Node | core.ExitType]:
        """Return the successor for a given node.

        Returns a propagated early exit of the same type in the case of a BashExit or BashReturn exit type.
        """
        if isinstance(exit_type, (BashExit, BashReturn)):
            return {exit_type}
        return self._cfg.get_successors(node, core.DEFAULT_EXIT)

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the line number and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        result["line num (in script)"] = {(None, str(self.definition["Pos"]["Line"]))}
        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result

    @staticmethod
    def create(
        and_cmd: bashparser_model.BinaryCmd, context: core.NonOwningContextRef[BashScriptContext]
    ) -> BashAndNode:
        """Create Bash and node from AND binary command AST.

        Parameters
        ----------
        and_cmd: bashparser_model.BinaryCmd
            Parsed AND binary command AST.
        context: core.NonOwningContextRef[BashScriptContext]
            Bash script context.
        """
        lhs = BashStatementNode(and_cmd["X"], context)
        rhs = BashStatementNode(and_cmd["Y"], context)
        return BashAndNode(definition=and_cmd, lhs=lhs, rhs=rhs, context=context)


class BashOrNode(core.ControlFlowGraphNode):
    """Control flow node representing a Bash OR ("||") binary command.

    Control flow structure consists of executing the left-hand side,
    followed by the right-hand side.

    (TODO model short circuit?)
    """

    #: Parsed OR binary command AST.
    definition: bashparser_model.BinaryCmd
    #: Left-hand side (first) command.
    lhs: BashStatementNode
    #: Right-hand side (second) command.
    rhs: BashStatementNode
    #: Bash script context.
    context: core.ContextRef[BashScriptContext]
    #: Control flow graph.
    _cfg: core.ControlFlowGraph

    def __init__(
        self,
        definition: bashparser_model.BinaryCmd,
        lhs: BashStatementNode,
        rhs: BashStatementNode,
        context: core.ContextRef[BashScriptContext],
    ) -> None:
        """Initialize Bash OR node.

        Typically, construction should be done via the create function rather than using this constructor directly.

        Parameters
        ----------
        definition: bashparser_model.BinaryCmd
            Parsed OR binary command AST.
        lhs: BashStatementNode
            Left-hand side (first) command.
        rhs: BashStatementNode
            Right-hand side (second) command.
        context: core.ContextRef[BashScriptContext]
            Bash script context.
        """
        super().__init__()
        self.definition = definition
        self.lhs = lhs
        self.rhs = rhs
        self.context = context

        self._cfg = core.ControlFlowGraph.create_from_sequence([lhs, rhs])

    def children(self) -> Iterator[core.Node]:
        """Yield the subcommands."""
        yield self.lhs
        yield self.rhs

    def get_entry(self) -> core.Node:
        """Return the entry node (the lhs node)."""
        return self._cfg.get_entry()

    def get_successors(self, node: core.Node, exit_type: core.ExitType) -> set[core.Node | core.ExitType]:
        """Return the successor for a given node.

        Returns a propagated early exit of the same type in the case of a BashExit or BashReturn exit type.
        """
        if isinstance(exit_type, (BashExit, BashReturn)):
            return {exit_type}
        return self._cfg.get_successors(node, core.DEFAULT_EXIT)

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table containing the line number and scopes."""
        result: dict[str, set[tuple[str | None, str]]] = {}
        result["line num (in script)"] = {(None, str(self.definition["Pos"]["Line"]))}
        printing.add_context_owned_scopes_to_properties_table(result, self.context)
        return result

    @staticmethod
    def create(or_cmd: bashparser_model.BinaryCmd, context: core.NonOwningContextRef[BashScriptContext]) -> BashOrNode:
        """Create Bash OR node from OR binary command AST.

        Parameters
        ----------
        and_cmd: bashparser_model.BinaryCmd
            Parsed AND binary command AST.
        context: core.NonOwningContextRef[BashScriptContext]
            Bash script context.
        """
        lhs = BashStatementNode(or_cmd["X"], context)
        rhs = BashStatementNode(or_cmd["Y"], context)
        return BashOrNode(definition=or_cmd, lhs=lhs, rhs=rhs, context=context)


class BashSingleCommandNode(core.InterpretationNode):
    """Interpretation node representing a single Bash command.

    Defines how to interpret the semantics of the different supported commands that
    may be invoked.
    """

    #: Parsed statement AST.
    definition: bashparser_model.Stmt
    #: Bash script context.
    context: core.ContextRef[BashScriptContext]
    #: Expression for command name.
    cmd: facts.Value
    #: Expressions for argument values (None if unrepresentable).
    args: list[facts.Value | None]
    #: Location expressions for where stdout is redirected to.
    stdout_redirects: set[facts.Location]

    def __init__(
        self,
        definition: bashparser_model.Stmt,
        context: core.ContextRef[BashScriptContext],
        cmd: facts.Value,
        args: list[facts.Value | None],
        stdout_redirects: set[facts.Location],
    ) -> None:
        """Initialize Bash single command node.

        Parameters
        ----------
        definition: bashparser_model.Stmt
            Parsed statement AST.
        context: core.ContextRef[BashScriptContext]
            Bash script context.
        cmd: facts.Value
            Expression for command name.
        args: list[facts.Value | None]
            Expressions for argument values (None if unrepresentable).
        stdout_redirects: set[facts.Location]
            Location expressions for where stdout is redirected to.
        """
        super().__init__()
        self.definition = definition
        self.context = context
        self.cmd = cmd
        self.args = args
        self.stdout_redirects = stdout_redirects

    def identify_interpretations(self, state: core.State) -> dict[core.InterpretationKey, Callable[[], core.Node]]:
        """Interpret the semantics of the different supported commands that may be invoked."""
        eval_transformer = evaluation.EvaluationTransformer(state)
        evaluated_writes = eval_transformer.transform_value(self.cmd)
        result: dict[core.InterpretationKey, Callable[[], core.Node]] = {}

        for resolved_cmd, bindings in evaluated_writes:
            match resolved_cmd:
                case facts.StringLiteral("echo"):
                    # Echo command, may have two different interpretations:
                    # - The concrete semantics of writing to the location its stdout is directed to
                    # - If writing to the special GitHub output var file, the higher-level semantics
                    #   of writing to the variable as specified in the echoed value.
                    if len(self.stdout_redirects) in {0, 1} and len(self.args) == 1:
                        first_arg = self.args[0]
                        stdout_redir = (
                            next(iter(self.stdout_redirects))
                            if len(self.stdout_redirects) == 1
                            else facts.Location(self.context.ref.stdout_scope.ref, self.context.ref.stdout_loc)
                        )
                        if first_arg is not None:
                            first_arg_val = first_arg

                            def build_echo(
                                stdout_redir: facts.Location = stdout_redir, first_arg_val: facts.Value = first_arg_val
                            ) -> core.Node:
                                return models.BashEchoNode(stdout_redir, first_arg_val)

                            github_context = self.context.ref.get_containing_github_context()

                            if (
                                self._is_github_output_loc(stdout_redir)
                                and github_context is not None
                                and github_context.output_var_prefix is not None
                            ):
                                output_var_prefix = github_context.output_var_prefix
                                job_variables_scope = github_context.job_context.ref.job_variables.ref
                                split = evaluation.parse_str_expr_split(first_arg, "=", maxsplit=1)
                                if len(split) == 2:

                                    def build_github_var_write(
                                        job_variables_scope: facts.Scope = job_variables_scope,
                                        output_var_prefix: str = output_var_prefix,
                                        split: list[facts.Value] = split,
                                    ) -> core.Node:
                                        return models.VarAssignNode(
                                            kind=models.VarAssignKind.GITHUB_JOB_VAR,
                                            var_scope=job_variables_scope,
                                            var_name=facts.BinaryStringOp.get_string_concat(
                                                facts.StringLiteral(output_var_prefix), split[0]
                                            ),
                                            value=split[1],
                                        )

                                    result[("echo_github_var", bindings)] = build_github_var_write

                            result[("echo", bindings)] = build_echo
                case facts.StringLiteral("mvn"):
                    # Maven build command.
                    for arg in self.args:
                        match arg:
                            case facts.StringLiteral(arg_lit):
                                if arg_lit in {"package", "install", "deploy", "verify"}:

                                    def build_mvn_build() -> core.Node:
                                        return models.MavenBuildModelNode(
                                            filesystem_scope=self.context.ref.filesystem.ref
                                        )

                                    result[("mvn", bindings)] = build_mvn_build
                case facts.StringLiteral("exit"):
                    # Exit command exits the script.
                    def build_exit_stmt() -> core.Node:
                        return BashExitNode()

                    result[("exit", bindings)] = build_exit_stmt
                case facts.StringLiteral("base64"):
                    # base64 command may encode or decode Base64 strings.

                    # TODO model other possibilities
                    if len(self.stdout_redirects) in {0, 1}:
                        stdout_redir = (
                            next(iter(self.stdout_redirects))
                            if len(self.stdout_redirects) == 1
                            else facts.Location(self.context.ref.stdout_scope.ref, self.context.ref.stdout_loc)
                        )
                        if len(self.args) == 0:

                            def build_base64_encode(stdout_redir: facts.Location = stdout_redir) -> core.Node:
                                return models.Base64EncodeNode(
                                    facts.Location(self.context.ref.stdin_scope.ref, self.context.ref.stdin_loc),
                                    stdout_redir,
                                )

                            result[("base64_encode", bindings)] = build_base64_encode
                        elif len(self.args) == 1 and (
                            self.args[0] == facts.StringLiteral("-d") or self.args[0] == facts.StringLiteral("--decode")
                        ):

                            def build_base64_decode(stdout_redir: facts.Location = stdout_redir) -> core.Node:
                                return models.Base64DecodeNode(
                                    facts.Location(self.context.ref.stdin_scope.ref, self.context.ref.stdin_loc),
                                    stdout_redir,
                                )

                            result[("base64_decode", bindings)] = build_base64_decode
                case facts.StringLiteral(cmd_name) if cmd_name.endswith(".sh"):
                    # Invoking another shell script.

                    # TODO pass arguments

                    repo_path = self.context.ref.get_containing_analysis_context().repo_path
                    if repo_path is not None:
                        # Check for path traversal patterns before analyzing a bash file.
                        # TODO working dir
                        bash_file_path = os.path.realpath(os.path.join(repo_path, "", cmd_name))
                        if os.path.exists(bash_file_path) and bash_file_path.startswith(repo_path):

                            def build_run_bash_script_file(bash_file_path: str = bash_file_path) -> core.Node:
                                bash_text = ""
                                with open(bash_file_path, encoding="utf-8") as bash_file:
                                    bash_text = bash_file.read()
                                return RawBashScriptNode(
                                    facts.StringLiteral(bash_text),
                                    core.OwningContextRef(
                                        BashScriptContext.create_from_bash_script(self.context, bash_file_path)
                                    ),
                                )

                            result[("run_file_bash_script", bindings)] = build_run_bash_script_file
                case facts.StringLiteral(cmd_name):
                    # If the command name is a defined shell function (as resolved from a read of the variable of that
                    # name in the function decl scope), then create a function call to the function definition stored
                    # in that variable.

                    evaluated_func_decls = evaluation.evaluate(
                        self,
                        facts.Read(
                            facts.Location(
                                scope=self.context.ref.func_decls.ref, loc=facts.Variable(facts.StringLiteral(cmd_name))
                            )
                        ),
                    )
                    for resolved_func, resolved_func_bindings in evaluated_func_decls:
                        if isinstance(resolved_func, facts.StringLiteral):
                            combined_func_bindings = evaluation.ReadBindings.combine_bindings(
                                [bindings, resolved_func_bindings]
                            )
                            if combined_func_bindings is not None:
                                resolved_func_json = resolved_func.literal

                                def build_func_call(func_json: str = resolved_func_json) -> core.Node:
                                    func_decl = cast(bashparser_model.FuncDecl, json.loads(func_json))
                                    return BashFuncCallNode(
                                        self.definition,
                                        func_decl,
                                        BashBlockNode.create([func_decl["Body"]], self.context.get_non_owned()),
                                        self.context,
                                    )

                                result[("function_call", combined_func_bindings)] = build_func_call

        def build_noop() -> core.Node:
            return core.NoOpStatementNode()

        if not isinstance(self.cmd, facts.StringLiteral) or len(result) == 0:
            result["default"] = build_noop

        return result

    def get_exit_state_transfer_filter(self) -> core.StateTransferFilter:
        """Return state transfer filter to clear scopes owned by this node after this node exits."""
        return core.ExcludedScopesStateTransferFilter(core.get_owned_scopes(self.context))

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties table.

        Contains the line number, command expression, argument expressions, stdout redirect location expressions, and scopes.
        """
        properties: dict[str, set[tuple[str | None, str]]] = {}
        properties["line num (in script)"] = {(None, str(self.definition["Pos"]["Line"]))}
        properties["cmd"] = {(None, self.cmd.to_datalog_fact_string())}
        for index, arg in enumerate(self.args):
            properties["arg" + str(index)] = {
                (None, arg.to_datalog_fact_string()) if arg is not None else (None, "UNKNOWN")
            }
        properties["stdout_redirects"] = {(None, x.to_datalog_fact_string()) for x in self.stdout_redirects}
        printing.add_context_owned_scopes_to_properties_table(properties, self.context)
        return properties

    @staticmethod
    def _is_github_output_loc(loc: facts.Location) -> bool:
        """Return whether the location is the special GitHub output variable file."""
        match loc:
            case facts.Location(
                _, facts.Filesystem(facts.Read(facts.Location(_, facts.Variable(facts.StringLiteral("GITHUB_OUTPUT")))))
            ):
                return True
        return False


class BashExitNode(core.StatementNode):
    """Statement node representing a Bash exit command.

    Always exits with the BashExit exit type (which causes the whole script to exit).
    """

    def apply_effects(self, before_state: core.State) -> dict[core.ExitType, core.State]:
        """Apply the effects of the Bash exit.

        Returns a BashExit exit state that is otherwise the same as the before state.
        """
        state = core.State()
        core.transfer_state(before_state, state)
        return {BASH_EXIT: state}


@dataclass(frozen=True)
class LiteralOrEnvVar:
    """Represents either a literal or a read of an environment variable."""

    #: Whether this represents an environment variable (or else a string literal).
    is_env_var: bool
    #: The environment variable name or string literal value.
    literal: str


def is_simple_var_read(param_exp: bashparser_model.ParamExp) -> bool:
    """Return whether expression is a simple env var read e.g. $ENV_VAR."""
    if param_exp.get("Excl", False) or param_exp.get("Length", False) or param_exp.get("Width", False):
        return False
    if (
        "Index" in param_exp
        or "Slice" in param_exp
        or "Repl" in param_exp
        or "Names" in param_exp
        or "Exp" in param_exp
    ):
        return False
    return True


def parse_env_var_read_word_part(part: bashparser_model.WordPart, allow_dbl_quoted: bool) -> str | None:
    """Parse word part as a read of an environment variable.

    If the given word part is a read of an env var (possibly enclosed in double quotes, if allowed),
    return the name of the variable, otherwise None.
    """
    if bashparser_model.is_dbl_quoted(part):
        if not allow_dbl_quoted:
            return None
        if "Parts" not in part or len(part["Parts"]) == 0:
            return ""
        if len(part["Parts"]) == 1:
            part = part["Parts"][0]
        else:
            return None

    if bashparser_model.is_param_exp(part):
        if not is_simple_var_read(part):
            return None
        return part["Param"]["Value"]

    return None


def parse_env_var_read_word(word: bashparser_model.Word, allow_dbl_quoted: bool) -> str | None:
    """Parse word as a read of an environment variable.

    If the given word is a read of an env var (possibly enclosed in double quotes, if allowed),
    return the name of the variable, otherwise None.
    """
    if len(word["Parts"]) == 1:
        part = word["Parts"][0]
        return parse_env_var_read_word_part(part, allow_dbl_quoted)
    return None


def parse_content(parts: list[bashparser_model.WordPart], allow_dbl_quoted: bool) -> list[LiteralOrEnvVar] | None:
    """Parse the given sequence of word parts.

    Return a representation as a sequence of string literal and env var reads, or else return None if not representable in this way.

    If allow_dbl_quoted is True, permit word parts to be double quoted expressions, the content of which will
    be included in the sequence (if False, return None if the sequence contains double quoted expressions).
    """
    content: list[LiteralOrEnvVar] = []
    for part in parts:
        env_var = parse_env_var_read_word_part(part, allow_dbl_quoted)
        if env_var is not None:
            content.append(LiteralOrEnvVar(is_env_var=True, literal=env_var))
        elif bashparser_model.is_lit(part):
            content.append(LiteralOrEnvVar(is_env_var=False, literal=part["Value"]))
        elif bashparser_model.is_dbl_quoted(part) and "Parts" in part:
            subcontent = parse_content(part["Parts"], False)
            if subcontent is None:
                return None
            content.extend(subcontent)
        else:
            return None
    return content


def convert_shell_value_sequence_to_fact_value(
    content: list[LiteralOrEnvVar], context: BashScriptContext
) -> facts.Value:
    """Convert sequence of Bash values into a single concatenated expression."""
    if len(content) == 0:
        raise CallGraphError("sequence cannot be empty")

    first_val = convert_shell_value_to_fact_value(content[0], context)
    if len(content) == 1:
        return first_val

    rest_val = convert_shell_value_sequence_to_fact_value(content[1:], context)

    return facts.BinaryStringOp(op=facts.BinaryStringOperator.STRING_CONCAT, operand1=first_val, operand2=rest_val)


def convert_shell_value_to_fact_value(val: LiteralOrEnvVar, context: BashScriptContext) -> facts.Value:
    """Convert a Bash literal or env var read into a value expression."""
    if val.is_env_var:
        return facts.Read(
            loc=facts.Location(scope=context.env.ref, loc=facts.Variable(name=facts.StringLiteral(literal=val.literal)))
        )
    return facts.StringLiteral(literal=val.literal)


def convert_shell_word_to_value(
    word: bashparser_model.Word, context: BashScriptContext
) -> tuple[facts.Value, bool] | None:
    """Convert a Bash word into a value expression.

    Return value expression alongside a bool indicating whether the value is
    "quoted" (or else may require further expansion post-resolution if "unquoted").
    """
    dbl_quoted_parts = parse_dbl_quoted_string(word)
    if dbl_quoted_parts is not None:
        return convert_shell_value_sequence_to_fact_value(dbl_quoted_parts, context), True

    sgl_quoted_str = parse_sql_quoted_string(word)
    if sgl_quoted_str is not None:
        return facts.StringLiteral(sgl_quoted_str), True

    singular_literal = parse_singular_literal(word)
    if singular_literal is not None:
        return facts.StringLiteral(literal=singular_literal), True

    single_var = parse_env_var_read_word(word, False)
    if single_var is not None:
        return convert_shell_value_to_fact_value(LiteralOrEnvVar(True, single_var), context), False

    return None


def parse_dbl_quoted_string(word: bashparser_model.Word) -> list[LiteralOrEnvVar] | None:
    """Parse double quoted string.

    If the given word is a double quoted expression, return
    a representation as a sequence of string literal and env var reads, or
    else return None if it is not a double quoted expression or if it is
    not representable in this way.
    """
    if len(word["Parts"]) == 1:
        part = word["Parts"][0]
        if bashparser_model.is_dbl_quoted(part) and "Parts" in part:
            return parse_content(part["Parts"], False)

    return None


def parse_sql_quoted_string(word: bashparser_model.Word) -> str | None:
    """Parse single quoted string.

    If the given word is a single quoted string, return the string
    literal content, otherwise return None.
    """
    if len(word["Parts"]) == 1:
        part = word["Parts"][0]
        if bashparser_model.is_sgl_quoted(part):
            return part["Value"]

    return None


def parse_singular_literal(word: bashparser_model.Word) -> str | None:
    """Parse singular literal word.

    If the given word is a single literal, return the string
    literal content, otherwise return None.
    """
    if len(word["Parts"]) == 1:
        part = word["Parts"][0]
        if bashparser_model.is_lit(part):
            return part["Value"]

    return None


# Cache for Bash expression parsing.
# note: not thread safe
_bashparser_cache: dict[str, list[bashparser_model.Word] | None] = {}


def parse_bash_expr(expr: str) -> list[bashparser_model.Word] | None:
    """Parse bash expression.

    Results are cached to avoid unnessary invocations of the Bash parser
    (since it requires spawning a separate process).
    """
    if expr in _bashparser_cache:
        return _bashparser_cache[expr]
    try:
        parse_result = bashparser.parse_expr(expr, MACARON_PATH)
        _bashparser_cache[expr] = parse_result
        return parse_result
    except ParseError:
        return None
