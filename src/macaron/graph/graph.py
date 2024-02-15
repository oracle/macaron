# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains generic methods for graph operations."""


from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")


def get_transitive_closure(
    node: T,
    get_successors: Callable[[T], Iterable[T]],
) -> Iterable[T]:
    """Return the set that contains `node` and nodes that can be transitively reached from it.

    This method obtains the successors of a node from `get_successors`. This `get_successors` function takes
    a node as input and returns a Collection of successors of that node.

    Parameters
    ----------
    node : T
        The start node to find the transitive successors.
    get_successors : Callable[[T], Iterable[T]]
        The function to obtain successors of every node.

    Returns
    -------
    Iterable[T]
        Contains `node` and its transitive successors.
    """
    visited = []
    stack = [node]

    while stack:
        current_node = stack[-1]

        if current_node not in visited:
            visited.append(current_node)

            for successor in get_successors(current_node):
                if successor not in visited:
                    stack.append(successor)

        else:
            stack.pop()

    return visited
