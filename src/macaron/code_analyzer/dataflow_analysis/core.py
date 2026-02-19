# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Core dataflow analysis framework definitions and algorithm."""

from __future__ import annotations

import functools
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from queue import Queue
from typing import Generic, Protocol, TypeGuard, TypeVar

from macaron.code_analyzer.dataflow_analysis import facts
from macaron.errors import CallGraphError

# Debug sequence number used to provide ordering information in debug graph.
# note: not thread safe
DEBUG_SEQUENCE_NUMBER = 0


def reset_debug_sequence_number() -> None:
    """Reset debug sequence number."""
    global DEBUG_SEQUENCE_NUMBER  # pylint: disable=global-statement
    DEBUG_SEQUENCE_NUMBER = 0


def get_debug_sequence_number() -> int:
    """Get current debug sequence number value."""
    return DEBUG_SEQUENCE_NUMBER


def increment_debug_sequence_number() -> None:
    """Increment debug sequence number."""
    global DEBUG_SEQUENCE_NUMBER  # pylint: disable=global-statement
    DEBUG_SEQUENCE_NUMBER = DEBUG_SEQUENCE_NUMBER + 1


@dataclass(frozen=True)
class StateDebugLabel:
    """Label for state fact providing information useful for debugging.

    Provides a record of analysis ordering and whether the fact was just copied
    from another state rather than newly produced.
    """

    #: Sequence number at time when state fact was created.
    sequence_number: int
    #: Whether the state fact is just copied from another state rather than newly produced."""
    copied: bool


class StateTransferFilter(ABC):
    """Interface for state transfer filters, which filter out state facts by location."""

    @abstractmethod
    def should_transfer(self, loc: facts.Location) -> bool:
        """Return whether facts with the given locations should be transferred or else filtered out."""


class State:
    """Representation of the abstract storage state at some program point.

    Consists of a set of abstract locations, each associated with a set of possible values.
    """

    #: Mapping of locations to a set of possible values.
    #: Values are annotated with a label containing info relevant for debugging
    state: dict[facts.Location, dict[facts.Value, StateDebugLabel]]

    def __init__(self) -> None:
        """Construct an empty state."""
        self.state = defaultdict(dict)


class DefaultStateTransferFilter(StateTransferFilter):
    """Default state transfer filter that includes all locations."""

    def should_transfer(self, loc: facts.Location) -> bool:
        """Transfer all locations."""
        return True


# Convenience instance of DefaultStateTransferFilter
DEFAULT_STATE_TRANSFER_FILTER = DefaultStateTransferFilter()


class ExcludedLocsStateTransferFilter(StateTransferFilter):
    """State transfer filter that excludes any locations in the given set."""

    #: Locations to exclude.
    excluded_locs: set[facts.Location]

    def __init__(self, excluded_locs: set[facts.Location]) -> None:
        """Construct filter that excludes the given locations."""
        self.excluded_locs = excluded_locs

    def should_transfer(self, loc: facts.Location) -> bool:
        """Return whether facts with the given locations should be transferred or else filtered out."""
        return loc not in self.excluded_locs


class ExcludedScopesStateTransferFilter(StateTransferFilter):
    """State transfer filter that excludes any locations that are within the scopes in the given set."""

    #: Scopes to exclude.
    excluded_scopes: set[facts.Scope]

    def __init__(self, excluded_scopes: set[facts.Scope]) -> None:
        """Construct filter that excludes the given scopes."""
        self.excluded_scopes = excluded_scopes

    def should_transfer(self, loc: facts.Location) -> bool:
        """Return whether facts with the given locations should be transferred or else filtered out."""
        return loc.scope not in self.excluded_scopes


def transfer_state(
    src_state: State,
    dest_state: State,
    transfer_filter: StateTransferFilter = DEFAULT_STATE_TRANSFER_FILTER,
    debug_is_copy: bool = True,
) -> bool:
    """Transfer/copy all facts in the src state to the dest state, except those excluded by the given filter.

    Parameters
    ----------
    src_state: State
        The state to transfer facts from.
    dest_state: State
        The state to modify by transferring facts to.
    transfer_filter: StateTransferFilter
        The filter to apply to the transferred facts (by default, transfer all).
    debug_is_copy: bool
        Whether the facts newly added to the dest state should be recorded as being copied or not (for debugging purposes).

    Returns
    -------
    bool
        Whether the dest state was modified.
    """
    changed = False
    for loc, vals in src_state.state.items():
        if not transfer_filter.should_transfer(loc):
            continue
        exit_vals = dest_state.state[loc]
        for val, label in vals.items():
            if val not in exit_vals:
                exit_vals[val] = StateDebugLabel(get_debug_sequence_number(), True if debug_is_copy else label.copied)
                changed = True
    return changed


class ExitType(ABC):
    """Representation of an exit type, describing the manner in which the execution of a node may terminate."""

    @abstractmethod
    def __hash__(self) -> int:
        pass

    @abstractmethod
    def __eq__(self, other: object) -> bool:
        pass


class DefaultExit(ExitType):
    """Default, normal exit."""

    def __hash__(self) -> int:
        return 19391

    def __eq__(self, other: object) -> bool:
        return isinstance(other, DefaultExit)


# Convenience instance of DefaultExit.
DEFAULT_EXIT = DefaultExit()


class Node(ABC):
    """Base class of all node types in dataflow analysis.

    Subclasses will represent the various program/semantic constructs,
    and define how to analyse them.
    """

    #: Abstract state at the point before the execution of this node.
    before_state: State

    #: Abstract state at the point after the execution of this node, for each possible distinct exit type.
    exit_states: dict[ExitType, State]

    #: Sequence number at the point the node was created, recorded for debugging purposes.
    created_debug_sequence_num: int
    #: Log of begin/end sequence numbers each time this node was processed, recorded for debugging purposes.
    processed_log: list[tuple[int, int]]

    def __init__(self) -> None:
        """Initialize with empty states."""
        self.before_state = State()
        self.exit_states = defaultdict(State)
        self.created_debug_sequence_num = get_debug_sequence_number()
        self.processed_log = []

    @abstractmethod
    def children(self) -> Iterator[Node]:
        """Yield the child nodes of this node."""

    @abstractmethod
    def analyse(self) -> bool:
        """Perform analysis of this node (and potentially any child nodes).

        Update the exit states with the analysis result.
        Returns whether anything was modified.
        """
        raise NotImplementedError

    def is_processed(self) -> bool:
        """Return whether this node has been processed."""
        return len(self.processed_log) > 0

    def notify_processed(self, begin_seq_num: int, end_seq_num: int) -> None:
        """Record that this node has been processed."""
        self.processed_log.append((begin_seq_num, end_seq_num))

    def get_exit_state_transfer_filter(self) -> StateTransferFilter:
        """Return the state transfer filter applicable to the exit state of this node.

        By default, nothing is excluded. Subclasses should override to provide appropriate filters
        to avoid transferring state that will be irrelevant after the node exits.
        """
        return DEFAULT_STATE_TRANSFER_FILTER

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: object) -> bool:
        return self is other

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a table of stringified properties, describing the details of this node, for debugging purposes.

        The returned properties table is a mapping of name to value-set, which can be rendered via the functions
        in the printing module.
        """
        return {}


def node_is_not_none(node: Node | None) -> TypeGuard[Node]:
    """Return whether the given node is not None."""
    return node is not None


def traverse_bfs(node: Node) -> Iterator[Node]:
    """Traverse the node tree in a breadth-first manner, yielding the nodes (including this node) in traversal order."""
    queue: Queue[Node] = Queue()
    queue.put(node)
    while not queue.empty() > 0:
        next_node = queue.get()
        yield next_node
        for child in next_node.children():
            queue.put(child)


def build_parent_mapping(node: Node) -> dict[Node, Node]:
    """Construct a mapping of nodes to their parent nodes."""
    parents: dict[Node, Node] = {}

    queue: Queue[Node] = Queue()
    queue.put(node)
    while not queue.empty():
        next_node = queue.get()
        for child in next_node.children():
            parents[child] = next_node
            queue.put(child)

    return parents


class NodeForest:
    """A collection of independent root nodes (with no control-flow or relation between them)."""

    #: Collection of root nodes.
    root_nodes: list[Node]
    #: Mapping of nodes to their parent nodes.
    parents: dict[Node, Node]

    def __init__(self, root_nodes: list[Node]) -> None:
        """Construct a NodeForest for the given nodes, and build the parent mapping."""
        self.root_nodes = root_nodes
        self.parents = {}
        for root_node in root_nodes:
            root_node_parents = build_parent_mapping(root_node)
            self.parents.update(root_node_parents)


class ControlFlowGraph:
    """Graph structure to represent control flow graphs."""

    #: Entry node.
    entry: Node
    #: Graph of successor edges.
    #: Each edge is from a particular exit of a particular node, either to a node or to an exit of the control flow itself.
    successors: dict[Node, dict[ExitType, set[Node | ExitType]]]

    def __init__(self, entry: Node) -> None:
        """Construct an initially-empty control flow graph."""
        self.entry = entry
        self.successors = defaultdict(lambda: defaultdict(set))

    def get_entry(self) -> Node:
        """Return the entry node."""
        return self.entry

    def add_successor(self, src: Node, exit_type: ExitType, dest: Node | ExitType) -> None:
        """Add a successor edge to the control flow graph."""
        self.successors[src][exit_type].add(dest)

    def get_successors(self, node: Node, exit_type: ExitType) -> set[Node | ExitType]:
        """Return the successors for a particular exit of a particular node."""
        return self.successors[node][exit_type]

    @staticmethod
    def create_from_sequence(seq: Sequence[Node]) -> ControlFlowGraph:
        """Construct a linear sequence of nodes."""
        if len(seq) == 0:
            raise CallGraphError("cannot create control flow graph from empty sequence")
        cfg = ControlFlowGraph(seq[0])
        prev_node = seq[0]
        for node in seq[1:]:
            cfg.add_successor(prev_node, DEFAULT_EXIT, node)
            prev_node = node

        cfg.add_successor(prev_node, DEFAULT_EXIT, DEFAULT_EXIT)

        return cfg


class ControlFlowGraphNode(Node):
    """Base class for nodes representing control-flow constructs.

    Defines the generic algorithm for analysing control flow graphs.
    Subclasses will define the child nodes and concrete graph structure.
    """

    def _propagate_edges(
        self,
        worklist: set[Node],
        src_state: State,
        state_transfer_filter: StateTransferFilter,
        successors: set[Node | ExitType],
    ) -> bool:
        changed = False
        for successor in successors:
            if isinstance(successor, Node):
                transfer_changed = transfer_state(src_state, successor.before_state, state_transfer_filter)
                changed = changed or transfer_changed
                if transfer_changed or not successor.is_processed():
                    worklist.add(successor)
            elif isinstance(successor, ExitType):
                changed = transfer_state(src_state, self.exit_states[successor], state_transfer_filter) or changed
        return changed

    def analyse(self) -> bool:
        """Perform analysis of this node.

        Performs analysis of the child nodes and propagates state from the exit state of an updated node to the before
        state of its successor nodes, according to the control-flow-graph structure, then analyses the successor nodes,
        and so on until a fixpoint is reached and no further updates may be made to any node states.

        Returns whether anything was modified.
        """
        begin_seq_num = get_debug_sequence_number()
        entry_node = self.get_entry()
        if entry_node is None:
            changed = transfer_state(self.before_state, self.exit_states[DEFAULT_EXIT])
            increment_debug_sequence_number()
            return changed

        changed = transfer_state(self.before_state, entry_node.before_state)
        increment_debug_sequence_number()

        worklist = {entry_node}

        while len(worklist) > 0:
            next_node = worklist.pop()
            next_changed = next_node.analyse()
            changed = changed or next_changed

            next_state_transfer_filter = next_node.get_exit_state_transfer_filter()

            for exit_type, exit_state in next_node.exit_states.items():
                successors = self.get_successors(next_node, exit_type)
                changed = self._propagate_edges(worklist, exit_state, next_state_transfer_filter, successors) or changed

            increment_debug_sequence_number()

        self.notify_processed(begin_seq_num, get_debug_sequence_number() - 1)
        return changed

    @abstractmethod
    def get_entry(self) -> Node | None:
        """Return the entry node."""

    @abstractmethod
    def get_successors(self, node: Node, exit_type: ExitType) -> set[Node | ExitType]:
        """Return the successors for a particular exit of a particular node."""


class StatementNode(Node):
    """Base class for nodes representing constructs with direct effects (and no child nodes).

    Subclasses will define the effects that apply when the node is executed.
    """

    def analyse(self) -> bool:
        """Perform analysis of this node, by applying the effects to update the after state.

        Returns whether anything was modified.
        """
        begin_seq_num = get_debug_sequence_number()
        new_exit_states = self.apply_effects(self.before_state)
        changed = False
        for new_exit_type, new_exit_state in new_exit_states.items():
            changed = transfer_state(new_exit_state, self.exit_states[new_exit_type], debug_is_copy=False) or changed

        self.notify_processed(begin_seq_num, get_debug_sequence_number())
        increment_debug_sequence_number()
        return changed

    def children(self) -> Iterator[Node]:
        """Yield nothing, as statements have no child nodes."""
        yield from ()

    @abstractmethod
    def apply_effects(self, before_state: State) -> dict[ExitType, State]:
        """Apply the effects of the statement, given the before state, returning the resulting exit state."""


class NoOpStatementNode(StatementNode):
    """Statement that has no effect."""

    def apply_effects(self, before_state: State) -> dict[ExitType, State]:
        """Apply the effects of the no-op, returning an exit state that is the same as the before state."""
        state = State()
        transfer_state(before_state, state)
        return {DEFAULT_EXIT: state}


class InterpretationKey(Protocol):
    """Interpretation key used to identify interpretations that have been produced before.

    Must support hashing and equality comparison to allow use as a dict key.
    """

    @abstractmethod
    def __hash__(self) -> int:
        pass

    @abstractmethod
    def __eq__(self, other: object, /) -> bool:
        pass


class InterpretationNode(Node):
    """Base class for nodes representing constructs requiring interpretation.

    Such constructs must be interpreted to produce possibly-multiple child nodes representing possible
    interpretations of the semantics of the node.

    Analysing the interpretation node will apply the combined effects of all of the possible interpretations.
    Subclasses will define how to identify the possible interpretations and generate the corresponding nodes.
    """

    #: The generated interpretations of this node, identified/deduplicated by some interpretation key.
    interpretations: dict[InterpretationKey, Node]

    def __init__(self) -> None:
        """Initialize node with no interpretations."""
        super().__init__()
        self.interpretations = {}

    def children(self) -> Iterator[Node]:
        """Yield each of the possible interpretations."""
        yield from self.interpretations.values()

    def update_interpretations(self) -> bool:
        """Analyse the node to identify interpretations.

        Analysis is done in the context of the current before state, adding any
        new interpretations generated to the interpretations dict.
        """
        latest_interpretations = self.identify_interpretations(self.before_state)
        new_interpretations = {x: y for (x, y) in latest_interpretations.items() if x not in self.interpretations}
        for new_interpretation, build_node in new_interpretations.items():
            self.interpretations[new_interpretation] = build_node()

        return len(new_interpretations) != 0

    @abstractmethod
    def identify_interpretations(self, state: State) -> dict[InterpretationKey, Callable[[], Node]]:
        """Analyse the node, in the context of the given before state, to identify interpretations.

        Returns, for each discovered interpretation, an identifying interpretation key that can be used
        to determine if the interpretation has been produced previously, and a callable that generates
        the node representing that interpretation (used to generate the node if the interpretation is new,
        otherwise the previously-generated node will be reused).
        """

    def analyse(self) -> bool:
        """Perform analysis of this node, by analysing each possible interpretation.

        Merges the exit states of each analysed interpretation to update the exit state of this node.

        Returns whether anything was modified.
        """
        begin_seq_num = get_debug_sequence_number()

        interpretations_changed = self.update_interpretations()

        increment_debug_sequence_number()

        sub_nodes_changed = False
        exit_changed = False

        key_transfer_changed: dict[InterpretationKey, bool] = {}

        for key, node in self.interpretations.items():
            transfer_changed = transfer_state(self.before_state, node.before_state)
            key_transfer_changed[key] = transfer_changed
            sub_nodes_changed = sub_nodes_changed or transfer_changed

        increment_debug_sequence_number()

        for key, node in self.interpretations.items():
            if key_transfer_changed[key] or not node.is_processed():
                analyse_changed = node.analyse()
                sub_nodes_changed = sub_nodes_changed or analyse_changed

        for node in self.interpretations.values():
            for exit_type, exit_state in node.exit_states.items():
                if exit_type not in self.exit_states:
                    exit_changed = True
                exit_changed = (
                    transfer_state(exit_state, self.exit_states[exit_type], node.get_exit_state_transfer_filter())
                    or exit_changed
                )

        self.notify_processed(begin_seq_num, get_debug_sequence_number())
        increment_debug_sequence_number()

        return interpretations_changed or sub_nodes_changed or exit_changed


R_co = TypeVar("R_co", covariant=True)


@dataclass(frozen=True)
class OwningContextRef(Generic[R_co]):
    """A reference to a part of a node's context that "owns" it.

    Ownership is used to identify what scopes are tied to a particular node
    such that they cease to exist or become irrelevant after the node exits,
    and thus any values stored in locations within those scopes may be erased
    from the state beyond that point to simplify the state.
    """

    ref: R_co

    def get_non_owned(self) -> NonOwningContextRef[R_co]:
        """Return a non owning reference to the same object."""
        return NonOwningContextRef(self.ref)


@dataclass(frozen=True)
class NonOwningContextRef(Generic[R_co]):
    """A reference to a part of a node's context that does not "own" it.

    Ownership is used to identify what scopes are tied to a particular node
    such that they cease to exist or become irrelevant after the node exits,
    and thus any values stored in locations within those scopes may be erased
    from the state beyond that point to simplify the state.
    """

    ref: R_co

    def get_non_owned(self) -> NonOwningContextRef[R_co]:
        """Return a non-owning reference to the same object."""
        return self


# A context ref may be owning or non-owning.
ContextRef = OwningContextRef[R_co] | NonOwningContextRef[R_co]


class Context(ABC):
    """Base class for node contexts.

    Represents the necessary context that influences the analysis of a node,
    primarily that of identifying the concrete scopes that fill particular
    roles in the node.
    """

    @abstractmethod
    def direct_refs(self) -> Iterator[ContextRef[Context] | ContextRef[facts.Scope]]:
        """Yield the direct references of the context, either to scopes or to other contexts."""

    def owned_scopes(self) -> Iterator[OwningContextRef[facts.Scope]]:
        """Yield the scopes that are owned by this context.

        Owned scopes are those that are directly referenced by owning references or scopes
        that are indirectly referenced by owning references, through referenced contexts that
        are referenced by owning references.
        """
        for ref in self.direct_refs():
            if isinstance(ref, OwningContextRef):
                if isinstance(ref.ref, Context):
                    yield from ref.ref.owned_scopes()
                else:
                    yield ref


@dataclass(frozen=True)
class AnalysisContext(Context):
    """Outermost context of the analysis.

    Records the path to the repo checkout, to allow the analysis access to files in the repo.
    """

    repo_path: str | None

    def direct_refs(self) -> Iterator[ContextRef[Context] | ContextRef[facts.Scope]]:
        """No direct references, yields nothing."""
        yield from []


class SimpleSequence(ControlFlowGraphNode):
    """Control-flow-graph node representing the execution of a sequence of nodes."""

    #: The sequence of nodes to execute.
    seq: list[Node]
    #: The control flow graph.
    _cfg: ControlFlowGraph

    def __init__(self, seq: list[Node]) -> None:
        """Construct control-flow-graph from sequence."""
        super().__init__()
        self.seq = seq
        self._cfg = ControlFlowGraph.create_from_sequence(seq)

    def children(self) -> Iterator[Node]:
        """Yield the nodes in the sequence."""
        yield from self.seq

    def get_entry(self) -> Node:
        """Return the entry node, the first in the sequence."""
        return self.seq[0]

    def get_successors(self, node: Node, exit_type: ExitType) -> set[Node | ExitType]:
        """Return the successor for a given node (the next in the sequence or the exit in the case of the last node)."""
        return self._cfg.get_successors(node, exit_type)


class SimpleAlternatives(InterpretationNode):
    """Interpretation node representing a concrete set of alternative nodes."""

    #: The alternatives.
    alts: list[Node]

    def __init__(self, alts: list[Node]) -> None:
        """Initialize node."""
        super().__init__()
        self.alts = alts

    def identify_interpretations(self, state: State) -> dict[InterpretationKey, Callable[[], Node]]:
        """Return the interpretations of this node, that is, each of the alternatives."""

        def get_alt(index: int) -> Node:
            return self.alts[index]

        return {i: functools.partial(get_alt, i) for i in range(0, len(self.alts))}


def get_owned_scopes(context: ContextRef[Context]) -> set[facts.Scope]:
    """Return the set of scopes owned via the given reference to a context.

    Returns empty if the given reference is non-owning.
    """
    match context:
        case OwningContextRef(ref):
            return {scope.ref for scope in ref.owned_scopes()}
        case NonOwningContextRef(ref):
            return set()
