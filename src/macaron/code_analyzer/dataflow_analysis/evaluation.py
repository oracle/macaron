# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Functions for evaluating and resolving dataflow analysis expressions."""

from __future__ import annotations

import base64
import os.path
from dataclasses import dataclass
from typing import TypeVar

from frozendict import frozendict

from macaron.code_analyzer.dataflow_analysis import bash, core, facts
from macaron.errors import CallGraphError


def evaluate(node: core.Node, value: facts.Value) -> set[tuple[facts.Value, ReadBindings]]:
    """Evaluate the given value, at the point immediately prior to the execution of the given node.

    Parameters
    ----------
    node: core.Node
        The node at which to evaluate the value (i.e. in the context of the before state of the node).
    value: facts.Value
        The value expression to evaluate.

    Returns
    -------
    set[tuple[facts.Value, ReadBindings]]
        The set of possible resolved values for the value expression, each with a record of the
        resolved value chosen for any read expressions.
    """
    eval_transformer = EvaluationTransformer(node.before_state)
    return eval_transformer.transform_value(value)


@dataclass(frozen=True)
class WriteStatement:
    """Representation of a write to a given location of a given value."""

    #: The location to write to.
    location: facts.Location
    #: The value to write.
    value: facts.Value

    def perform_write(self, before_state: core.State) -> tuple[core.State, set[facts.Location]]:
        """Return a state containing only the values stored by the write operation, in context of the before state.

        Also returns the set of locations within that state which should be considered to have been overwritten,
        erasing any previous values.
        """
        eval_transformer = EvaluationTransformer(before_state)
        written_state = core.State()
        evaluated_writes = eval_transformer.transform_write(self.location, self.value)
        for loc, val, _ in evaluated_writes:
            written_state.state[loc][val] = core.StateDebugLabel(core.get_debug_sequence_number(), False)
        # Currently, never erases previous values.
        return (written_state, set())


@dataclass(frozen=True)
class StatementSet:
    """Representation of a set of (simultaneous) write operations."""

    #: The set of writes.
    stmts: set[WriteStatement]

    def apply_effects(self, before_state: core.State) -> core.State:
        """Apply the effect of the set of writes, returning the resulting state."""
        final_state = core.State()
        final_overwritten_locs: set[facts.Location] = set()
        for stmt in self.stmts:
            written_state, overwritten_locs = stmt.perform_write(before_state)
            for loc in overwritten_locs:
                final_overwritten_locs.add(loc)
            core.transfer_state(written_state, final_state, debug_is_copy=False)

        core.transfer_state(before_state, final_state, core.ExcludedLocsStateTransferFilter(final_overwritten_locs))
        return final_state

    @staticmethod
    def union(*stmt_sets: StatementSet) -> StatementSet:
        """Combine multiple write sets into one."""
        stmts: set[WriteStatement] = set()
        for stmt_set in stmt_sets:
            for stmt in stmt_set.stmts:
                stmts.add(stmt)
        return StatementSet(stmts)


class ParameterPlaceholderTransformer:
    """Expression transformer which replaces parameter placeholders with their corresponding bound values."""

    #: Whether to raise an exception if a parameter is found with no provided binding.
    allow_unbound_params: bool
    #: Bindings for value parameter placeholders, mapping parameter name to bound value expression.
    value_parameter_binds: dict[str, facts.Value]
    #: Bindings for location parameter placeholders, mapping parameter name to bound location expression.
    location_parameter_binds: dict[str, facts.LocationSpecifier]
    #: Bindings for scope parameter placeholders, mapping parameter name to bound scope.
    scope_parameter_binds: dict[str, facts.Scope]

    def __init__(
        self,
        allow_unbound_params: bool = True,
        value_parameter_binds: dict[str, facts.Value] | None = None,
        location_parameter_binds: dict[str, facts.LocationSpecifier] | None = None,
        scope_parameter_binds: dict[str, facts.Scope] | None = None,
    ) -> None:
        """Initialize transformer with bindings.

        Parameters
        ----------
        allow_unbound_params: bool
            Whether to raise an exception if a parameter is found with no provided binding.
        value_parameter_binds: dict[str, facts.Value] | None
            Bindings for value parameter placeholders, mapping parameter name to bound value expression.
        location_parameter_binds: dict[str, facts.Value] | None
            Bindings for location parameter placeholders, mapping parameter name to bound location expression.
        scope_parameter_binds: dict[str, facts.Value] | None
            Bindings for scope parameter placeholders, mapping parameter name to bound scope.
        """
        self.allow_unbound_params = allow_unbound_params
        self.value_parameter_binds = value_parameter_binds or {}
        self.location_parameter_binds = location_parameter_binds or {}
        self.scope_parameter_binds = scope_parameter_binds or {}

    def transform_value(self, value: facts.Value) -> facts.Value:
        """Transform given value expression.

        Returns a value expression with any parameter placeholders replaced with their bound values.
        """
        match value:
            case facts.StringLiteral(_):
                return value
            case facts.Read(loc):
                new_loc = self.transform_location(loc)
                if new_loc is loc:
                    return value
                return facts.Read(new_loc)
            case facts.ArbitraryNewData(_):
                return value
            case facts.UnaryStringOp(op, operand):
                new_operand = self.transform_value(operand)
                if new_operand is operand:
                    return value
                return facts.UnaryStringOp(op, new_operand)
            case facts.BinaryStringOp(op, operand1, operand2):
                new_operand1 = self.transform_value(operand1)
                new_operand2 = self.transform_value(operand2)

                if op == facts.BinaryStringOperator.STRING_CONCAT:
                    return facts.BinaryStringOp.get_string_concat(new_operand1, new_operand2)

                # if new_operand1 is operand1 and new_operand2 is operand2:
                #     return value
                # return facts.BinaryStringOp(op, new_operand1, new_operand2)
            case facts.ParameterPlaceholderValue(name):
                if name in self.value_parameter_binds:
                    return self.value_parameter_binds[name]
                if not self.allow_unbound_params:
                    raise CallGraphError("unbound value parameter: " + name)
                return value
            case facts.InstalledPackage(name, version, distribution, url):
                new_name = self.transform_value(name)
                new_version = self.transform_value(version)
                new_distribution = self.transform_value(distribution)
                new_url = self.transform_value(url)
                if new_name is name and new_version is version and new_distribution is distribution and new_url is url:
                    return value
                return facts.InstalledPackage(new_name, new_version, new_distribution, new_url)
            case facts.SingleBashTokenConstraint(val):
                new_val = self.transform_value(val)
                if new_val is val:
                    return value
                return facts.SingleBashTokenConstraint(new_val)
            case facts.Symbolic(sym_val):
                new_sym_val = self.transform_value(sym_val)
                if new_sym_val is sym_val:
                    return value
                return facts.Symbolic(new_sym_val)
        raise CallGraphError("unknown facts.Value type: " + value.__class__.__name__)

    def transform_location(self, location: facts.Location) -> facts.Location:
        """Transform given location expression.

        Returns a location expression with any parameter placeholders replaced with their bound values.
        """
        new_scope = self.transform_scope(location.scope)
        new_location_spec = self.transform_location_specifier(location.loc)
        if new_scope is location.scope and new_location_spec is location.loc:
            return location
        return facts.Location(new_scope, new_location_spec)

    def transform_location_specifier(self, location: facts.LocationSpecifier) -> facts.LocationSpecifier:
        """Transform given location specifier expression.

        Returns a location specifier expression with any parameter placeholders replaced with their bound values.
        """
        match location:
            case facts.Filesystem(path):
                new_path = self.transform_value(path)
                if new_path is path:
                    return location
                return facts.Filesystem(new_path)
            case facts.Variable(name):
                new_name = self.transform_value(name)
                if new_name is name:
                    return location
                return facts.Variable(new_name)
            case facts.Artifact(name, file):
                new_name = self.transform_value(name)
                new_file = self.transform_value(file)
                if new_name is name and new_file is file:
                    return location
                return facts.Artifact(new_name, new_file)
            case facts.FilesystemAnyUnderDir(path):
                new_path = self.transform_value(path)
                if new_path is path:
                    return location
                return facts.FilesystemAnyUnderDir(new_path)
            case facts.ArtifactAnyFilename(name):
                new_name = self.transform_value(name)
                if new_name is name:
                    return location
                return facts.ArtifactAnyFilename(new_name)
            case facts.ParameterPlaceholderLocation(name):
                if name in self.location_parameter_binds:
                    return self.location_parameter_binds[name]
                if not self.allow_unbound_params:
                    raise CallGraphError("unbound location parameter: " + name)
                return location
            case facts.Console():
                return location
            case facts.Installed(name):
                new_name = self.transform_value(name)
                if new_name is name:
                    return location
                return facts.Installed(new_name)
        raise CallGraphError("unknown location type: " + location.__class__.__name__)

    def transform_scope(self, scope: facts.Scope) -> facts.Scope:
        """Transform given scope.

        Returns a scope with any parameter placeholders replaced with their bound values.
        """
        if isinstance(scope, facts.ParameterPlaceholderScope):
            if scope.name in self.scope_parameter_binds:
                return self.scope_parameter_binds[scope.name]
            if not self.allow_unbound_params:
                raise CallGraphError("unbound scope parameter: " + scope.name)
        return scope

    def transform_statement(self, statement: WriteStatement) -> WriteStatement:
        """Transform given write statement.

        Returns a write statement with any parameter placeholders replaced with their bound values.
        """
        new_location = self.transform_location(statement.location)
        new_value = self.transform_value(statement.value)
        if new_location is statement.location and new_value is statement.value:
            return statement
        return WriteStatement(new_location, new_value)

    def transform_statement_set(self, statement_set: StatementSet) -> StatementSet:
        """Transform given write statement set.

        Returns a write statement set with any parameter placeholders replaced with their bound values.
        """
        changed = False
        new_stmts: set[WriteStatement] = set()
        for stmt in statement_set.stmts:
            new_stmt = self.transform_statement(stmt)
            if new_stmt is not stmt:
                changed = True
            new_stmts.add(new_stmt)

        if not changed:
            return statement_set
        return StatementSet(new_stmts)


T = TypeVar("T")


def is_singleton(s: set[T], e: T) -> bool:
    """Return whether the given set contains only the single given element."""
    return len(s) == 1 and next(iter(s)) == e


def is_singleton_no_bindings(s: set[tuple[T, ReadBindings]], e: T) -> bool:
    """Return whether the given set contains only the single given element with no read bindings."""
    return len(s) == 1 and next(iter(s)) == (e, READBINDINGS_EMPTY)


def scope_matches(read_scope: facts.Scope, stored_scope: facts.Scope) -> bool:
    """Return whether the given read scope matches the given stored scope.

    Matching means that a read of the read scope may return values from the stored scope.
    """
    cur_scope: facts.Scope | None = read_scope
    while cur_scope is not None:
        if cur_scope == stored_scope:
            return True
        cur_scope = cur_scope.outer_scope
    return False


def location_subsumes(loc: facts.LocationSpecifier, subloc: facts.LocationSpecifier) -> bool:
    """Return whether the given location subsumes the given sub location.

    Subsumption means that a read of subloc may be considered to be a read of loc or some part thereof.
    """
    if loc == subloc:
        return True

    match loc, subloc:
        case facts.Filesystem(facts.StringLiteral(loc_path_lit)), facts.Filesystem(
            facts.StringLiteral(subloc_path_lit)
        ):
            # Ignore superficial differences in file path due to "./" relative paths.
            if (
                not loc_path_lit.startswith("/")
                and not subloc_path_lit.startswith("/")
                and loc_path_lit.removeprefix("./") == subloc_path_lit.removeprefix("./")
            ):
                return True
        case facts.FilesystemAnyUnderDir(facts.StringLiteral(dir_lit)), facts.Filesystem(
            facts.StringLiteral(subloc_path_lit)
        ):
            # A file path under the same dir as a FilesystemAnyUnderDir is subsumed.
            if subloc_path_lit.startswith(dir_lit.removesuffix("/") + "/"):
                return True
    return False


def get_values_for_subsumed_read(
    read_loc: facts.LocationSpecifier, state_loc: facts.LocationSpecifier, state_vals: set[facts.Value]
) -> set[facts.Value]:
    """Return the set of values stored in the state location, if relevant for the given read location."""
    match read_loc, state_loc:
        case facts.ArtifactAnyFilename(read_artifact_name), facts.Artifact(state_artifact_name, state_artifact_file):
            if read_artifact_name == state_artifact_name:
                return {state_artifact_file}

    if location_subsumes(state_loc, read_loc):
        return state_vals

    return set()


class ReadBindings:
    """Set of bindings of read expressions to values bound as the result of those read expressions."""

    #: Mapping of read expressions to bound values.
    bindings: frozendict[facts.Read, facts.Value]

    def __init__(self, binds: frozendict[facts.Read, facts.Value] | None = None) -> None:
        """Initialize with given bindings."""
        self.bindings = binds or frozendict()

    def __len__(self) -> int:
        """Return the number of bindings in the set."""
        return len(self.bindings)

    def with_binding(self, read: facts.Read, value: facts.Value) -> ReadBindings | None:
        """Return bindings with the given additional binding, or None if the bindings conflict."""
        if read in self.bindings:
            if self.bindings[read] != value:
                return None
            return self
        new_binds = self.bindings.set(read, value)
        return ReadBindings(new_binds)

    def with_bindings(self, bindings: ReadBindings) -> ReadBindings | None:
        """Return bindings with the given additional bindings, or None if the bindings conflict."""
        if len(bindings) == 0:
            return self
        if len(self) == 0:
            return bindings

        for read, val in bindings.bindings.items():
            if read in self.bindings:
                if self.bindings[read] != val:
                    return None

        combined_bindings = frozendict({**self.bindings, **bindings.bindings})
        return ReadBindings(combined_bindings)

    @staticmethod
    def combine_bindings(bindings_list: list[ReadBindings]) -> ReadBindings | None:
        """Return bindings combining all bindings in the given list, or None if the bindings conflict."""
        if len(bindings_list) == 0:
            return READBINDINGS_EMPTY

        cur_binding: ReadBindings | None = bindings_list[0]
        for bindings in bindings_list[1:]:
            cur_binding = cur_binding.with_bindings(bindings) if cur_binding is not None else None
            if cur_binding is None:
                return None
        return cur_binding

    def __hash__(self) -> int:
        return hash(self.bindings)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ReadBindings):
            return self.bindings == other.bindings
        return False

    def __repr__(self) -> str:
        return str(self.bindings)


# Convenience instance of empty bindings.
READBINDINGS_EMPTY = ReadBindings()


class EvaluationTransformer:
    """Expression transformer which evaluates the expression to produce a set of resolved values.

    The expression is evaluated in the context of a specified abstract storage state.
    """

    #: The state from which to resolve reads.
    state: core.State

    def __init__(self, state: core.State) -> None:
        """Initialize transformer with state from which to resolve reads."""
        self.state = state

    def transform_write(
        self, location: facts.Location, value: facts.Value
    ) -> set[tuple[facts.Location, facts.Value, ReadBindings]]:
        """Transform a write location and value, returning the set of resolved values with the necessary bindings."""
        evaluated_locations = self.transform_location(location)
        evaluated_values = self.transform_value(value)
        result: set[tuple[facts.Location, facts.Value, ReadBindings]] = set()
        for loc, loc_bindings in evaluated_locations:
            for val, val_bindings in evaluated_values:
                combined_bindings = loc_bindings.with_bindings(val_bindings)
                if combined_bindings is not None:
                    result.add((loc, val, combined_bindings))
        return result

    def transform_value(self, value: facts.Value) -> set[tuple[facts.Value, ReadBindings]]:
        """Transform a value expression, returning the set of resolved values with the necessary bindings."""
        match value:
            case facts.StringLiteral(_):
                return {(value, READBINDINGS_EMPTY)}
            case facts.Read(loc):
                # Read values from the state.
                new_locs = self.transform_location(loc)
                read_vals: set[tuple[facts.Value, ReadBindings]] = set()
                for new_loc, new_loc_bindings in new_locs:
                    read_vals.add((facts.Symbolic(facts.Read(new_loc)), new_loc_bindings))

                    for state_loc, state_vals in self.state.state.items():
                        if scope_matches(new_loc.scope, state_loc.scope):
                            for read_val in get_values_for_subsumed_read(
                                new_loc.loc, state_loc.loc, set(state_vals.keys())
                            ):
                                combined_bindings = new_loc_bindings.with_binding(value, read_val)
                                if combined_bindings is not None:
                                    read_vals.add((read_val, combined_bindings))
                return read_vals
            case facts.ArbitraryNewData(_):
                return {(value, READBINDINGS_EMPTY)}
            case facts.UnaryStringOp(op, operand):
                new_operands = self.transform_value(operand)
                if op == facts.UnaryStringOperator.BASENAME:
                    # Concretely evaluate basename operator for string literal.
                    basename_result: set[tuple[facts.Value, ReadBindings]] = set()
                    for new_operand, new_operand_bindings in new_operands:
                        if isinstance(new_operand, facts.StringLiteral):
                            basename_result.add(
                                (facts.StringLiteral(os.path.basename(new_operand.literal)), new_operand_bindings)
                            )
                    return basename_result
                if op == facts.UnaryStringOperator.BASE64DECODE:
                    # Concretely evaluate base64 decode operator for string literal
                    base64_decode_result: set[tuple[facts.Value, ReadBindings]] = set()
                    for new_operand, new_operand_bindings in new_operands:
                        if isinstance(new_operand, facts.StringLiteral):
                            base64_decode_result.add(
                                (
                                    facts.StringLiteral(base64.b64decode(new_operand.literal).decode("utf-8")),
                                    new_operand_bindings,
                                )
                            )
                    return base64_decode_result
                return set()
            case facts.BinaryStringOp(op, operand1, operand2):
                new_operand1s = self.transform_value(operand1)
                new_operand2s = self.transform_value(operand2)
                if op == facts.BinaryStringOperator.STRING_CONCAT:
                    # Concretely evaluate string concatenation for concat of 2 string literals.
                    concat_result: set[tuple[facts.Value, ReadBindings]] = set()
                    for new_operand1, new_operand1_bindings in new_operand1s:
                        for new_operand2, new_operand2_bindings in new_operand2s:
                            if isinstance(new_operand1, facts.StringLiteral) and isinstance(
                                new_operand2, facts.StringLiteral
                            ):
                                combined_bindings = new_operand1_bindings.with_bindings(new_operand2_bindings)
                                if combined_bindings is not None:
                                    # TODO Have some truncated symbolic representation for
                                    # excessively long strings rather than just dropping them.
                                    if len(new_operand1.literal) + len(new_operand2.literal) < 10000:
                                        concat_result.add(
                                            (
                                                facts.StringLiteral(new_operand1.literal + new_operand2.literal),
                                                combined_bindings,
                                            )
                                        )
                    return concat_result

                # return set()
            case facts.SingleBashTokenConstraint(operand):
                # For single bash token constraint, to evaluate a string literal, the literal is parsed
                # as a bash expression, and if that results in a single element, then the constraint
                # is met and the unmodified literal is returned, if it parses as multiple elements, then
                # no resolved values are produced for that literal.
                #
                # Otherwise returns the constrained expression as is, while simplifying redundant
                # multiply-nested constraints.
                #
                new_operands = self.transform_value(operand)
                constraint_result: set[tuple[facts.Value, ReadBindings]] = set()
                for new_operand, new_operand_bindings in new_operands:
                    match new_operand:
                        case facts.StringLiteral(lit):
                            parsed_bash_expr = bash.parse_bash_expr(lit)
                            if parsed_bash_expr is not None and len(parsed_bash_expr) == 1:
                                constraint_result.add((new_operand, new_operand_bindings))

                        case facts.SingleBashTokenConstraint(suboperand):
                            constraint_result.add((facts.SingleBashTokenConstraint(suboperand), new_operand_bindings))
                        case _:
                            constraint_result.add((facts.SingleBashTokenConstraint(new_operand), new_operand_bindings))
                return constraint_result
            case facts.ParameterPlaceholderValue(name):
                return set()
            case facts.InstalledPackage(name, version, distribution, url):
                # Resolve parameters and return every combination.
                new_names = self.transform_value(name)
                new_versions = self.transform_value(version)
                new_distributions = self.transform_value(distribution)
                new_urls = self.transform_value(url)
                if (
                    is_singleton_no_bindings(new_names, name)
                    and is_singleton_no_bindings(new_versions, version)
                    and is_singleton_no_bindings(new_distributions, distribution)
                    and is_singleton_no_bindings(new_urls, url)
                ):
                    return {(value, READBINDINGS_EMPTY)}
                result: set[tuple[facts.Value, ReadBindings]] = set()
                for new_name, new_name_bindings in new_names:
                    for new_version, new_version_bindings in new_versions:
                        version_combined_bindings = new_name_bindings.with_bindings(new_version_bindings)
                        if version_combined_bindings is None:
                            continue
                        for new_distribution, new_distribution_bindings in new_distributions:
                            distribution_combined_bindings = version_combined_bindings.with_bindings(
                                new_distribution_bindings
                            )
                            if distribution_combined_bindings is None:
                                continue
                            for new_url, new_url_bindings in new_urls:
                                url_combined_bindings = distribution_combined_bindings.with_bindings(new_url_bindings)
                                if url_combined_bindings is not None:
                                    result.add(
                                        (
                                            facts.InstalledPackage(new_name, new_version, new_distribution, new_url),
                                            url_combined_bindings,
                                        )
                                    )
                return result
            case facts.Symbolic(_):
                return {(value, READBINDINGS_EMPTY)}
        raise CallGraphError("unknown facts.Value type: " + value.__class__.__name__)

    def transform_location(self, location: facts.Location) -> set[tuple[facts.Location, ReadBindings]]:
        """Transform a location expression, returning the set of resolved values with the necessary bindings."""
        new_location_specs = self.transform_location_specifier(location.loc)
        if is_singleton_no_bindings(new_location_specs, location.loc):
            return {(location, READBINDINGS_EMPTY)}
        return {
            (facts.Location(location.scope, new_location_spec), new_location_spec_bindings)
            for new_location_spec, new_location_spec_bindings in new_location_specs
        }

    def transform_location_specifier(
        self, location: facts.LocationSpecifier
    ) -> set[tuple[facts.LocationSpecifier, ReadBindings]]:
        """Transform a location specifier expression, returning the set of resolved values with the necessary bindings."""
        match location:
            case facts.Filesystem(path):
                new_paths = self.transform_value(path)
                if is_singleton_no_bindings(new_paths, path):
                    return {(location, READBINDINGS_EMPTY)}
                return {(facts.Filesystem(new_path), new_path_bindings) for new_path, new_path_bindings in new_paths}
            case facts.Variable(name):
                new_names = self.transform_value(name)
                if is_singleton_no_bindings(new_names, name):
                    return {(location, READBINDINGS_EMPTY)}
                return {(facts.Variable(new_name), new_name_bindings) for new_name, new_name_bindings in new_names}
            case facts.Artifact(name, file):
                new_names = self.transform_value(name)
                new_files = self.transform_value(file)
                if is_singleton_no_bindings(new_names, name) and is_singleton_no_bindings(new_files, file):
                    return {(location, READBINDINGS_EMPTY)}
                artifact_result: set[tuple[facts.LocationSpecifier, ReadBindings]] = set()
                for new_name, new_name_bindings in new_names:
                    for new_file, new_file_bindings in new_files:
                        combined_bindings = new_name_bindings.with_bindings(new_file_bindings)
                        if combined_bindings is not None:
                            artifact_result.add((facts.Artifact(new_name, new_file), combined_bindings))
                return artifact_result
            case facts.FilesystemAnyUnderDir(path):
                new_paths = self.transform_value(path)
                if is_singleton_no_bindings(new_paths, path):
                    return {(location, READBINDINGS_EMPTY)}
                return {
                    (facts.FilesystemAnyUnderDir(new_path), new_path_bindings)
                    for new_path, new_path_bindings in new_paths
                }
            case facts.ArtifactAnyFilename(name):
                new_names = self.transform_value(name)
                if is_singleton_no_bindings(new_names, name):
                    return {(location, READBINDINGS_EMPTY)}
                return {
                    (facts.FilesystemAnyUnderDir(new_name), new_name_bindings)
                    for new_name, new_name_bindings in new_names
                }
            case facts.ParameterPlaceholderLocation(name):
                return {(location, READBINDINGS_EMPTY)}
            case facts.Console():
                return {(location, READBINDINGS_EMPTY)}
            case facts.Installed(name):
                new_names = self.transform_value(name)
                return {(facts.Installed(new_name), new_name_bindings) for new_name, new_name_bindings in new_names}
        raise CallGraphError("unknown location type: " + location.__class__.__name__)


# TODO generalise visitors
class ContainsSymbolicVisitor:
    """Visitor to determine whether a given expression contains any symbolic expressions."""

    def visit_value(self, value: facts.Value) -> bool:
        """Search value expression for symbolic expressions and return whether any were found."""
        match value:
            case facts.StringLiteral(_):
                return False
            case facts.Read(loc):
                return self.visit_location(loc)
            case facts.ArbitraryNewData(_):
                return False
            case facts.UnaryStringOp(_, operand):
                return self.visit_value(operand)
            case facts.BinaryStringOp(_, operand1, operand2):
                return self.visit_value(operand1) or self.visit_value(operand2)
            case facts.ParameterPlaceholderValue(name):
                return False
            case facts.InstalledPackage(name, version, distribution, url):
                return (
                    self.visit_value(name)
                    or self.visit_value(version)
                    or self.visit_value(distribution)
                    or self.visit_value(url)
                )
            case facts.SingleBashTokenConstraint(operand):
                return self.visit_value(operand)
            case facts.Symbolic(_):
                return True
        raise CallGraphError("unknown facts.Value type: " + value.__class__.__name__)

    def visit_location(self, location: facts.Location) -> bool:
        """Search location expression for symbolic expressions and return whether any were found."""
        return self.visit_location_specifier(location.loc)

    def visit_location_specifier(self, location: facts.LocationSpecifier) -> bool:
        """Search location specifier expression for symbolic expressions and return whether any were found."""
        match location:
            case facts.Filesystem(path):
                return self.visit_value(path)
            case facts.Variable(name):
                return self.visit_value(name)
            case facts.Artifact(name, file):
                return self.visit_value(name) or self.visit_value(file)
            case facts.FilesystemAnyUnderDir(path):
                return self.visit_value(path)
            case facts.ArtifactAnyFilename(name):
                return self.visit_value(name)
            case facts.ParameterPlaceholderLocation(name):
                return False
            case facts.Console():
                return False
            case facts.Installed(name):
                return self.visit_value(name)
        raise CallGraphError("unknown location type: " + location.__class__.__name__)


def filter_symbolic_values(values: set[tuple[facts.Value, ReadBindings]]) -> set[tuple[facts.Value, ReadBindings]]:
    """Filter out symbolic values.

    Returns a set containing all elements from the given set that do not contain any symbolic expressions.
    """
    return {val for val in values if not ContainsSymbolicVisitor().visit_value(val[0])}


def filter_symbolic_locations(
    locs: set[tuple[facts.Location, ReadBindings]],
) -> set[tuple[facts.Location, ReadBindings]]:
    """Filter out symbolic locations.

    Returns a set containing all elements from the given set that do not contain any symbolic expressions.
    """
    return {loc for loc in locs if not ContainsSymbolicVisitor().visit_location(loc[0])}


def filter_symbolic_location_specifiers(
    locs: set[tuple[facts.LocationSpecifier, ReadBindings]],
) -> set[tuple[facts.LocationSpecifier, ReadBindings]]:
    """Filter out symbolic location specifiers.

    Returns a set containing all elements from the given set that do not contain any symbolic expressions.
    """
    return {loc for loc in locs if not ContainsSymbolicVisitor().visit_location_specifier(loc[0])}


def get_single_resolved_str(resolved_values: set[tuple[facts.Value, ReadBindings]]) -> str | None:
    """If the given set contains only a single string literal value, return that string, or else None."""
    resolved_values = filter_symbolic_values(resolved_values)
    if len(resolved_values) == 1:
        val = next(iter(resolved_values))[0]
        if isinstance(val, facts.StringLiteral):
            return val.literal
    return None


def get_single_resolved_str_with_default(
    resolved_values: set[tuple[facts.Value, ReadBindings]], default_value: str
) -> str:
    """If the given set contains only a single string literal value, return that string, else return default value."""
    result = get_single_resolved_str(resolved_values)
    if result is not None:
        return result
    return default_value


def parse_str_expr_split(str_expr: facts.Value, delimiter_char: str, maxsplit: int = -1) -> list[facts.Value]:
    """Split a string expression on the appearance of the delimiter char in literal parts of the expression."""
    if len(delimiter_char) != 1:
        raise CallGraphError("delimiter_char must be single char")

    match str_expr:
        case facts.StringLiteral(literal):
            split_str = literal.split(delimiter_char, maxsplit=maxsplit)
            return [facts.StringLiteral(s) for s in split_str]
        case facts.BinaryStringOp(facts.BinaryStringOperator.STRING_CONCAT, o1, o2):
            split_lhs = parse_str_expr_split(o1, delimiter_char, maxsplit)
            split_rhs = parse_str_expr_split(
                o2, delimiter_char, -1 if maxsplit == -1 else maxsplit - (len(split_lhs) - 1)
            )
            if len(split_lhs) == 1 and len(split_rhs) == 1:
                return [str_expr]
            return (
                split_lhs[:-1] + [facts.BinaryStringOp.get_string_concat(split_lhs[-1], split_rhs[0])] + split_rhs[1:]
            )
    return [str_expr]
