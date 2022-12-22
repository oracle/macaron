# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains classes to generate build call graphs for the target repository."""

from collections.abc import Iterable
from typing import Generic, TypeVar

Node = TypeVar("Node", bound="BaseNode")
"""This binds type ``Node`` to ``BaseNode`` and any of its subclasses.

Therefore, any node of type ``Node`` that is stored in the call graph
container will be a subtype of ``BaseNode``.
"""


class BaseNode(Generic[Node]):
    """This is the generic class for call graph nodes."""

    def __init__(self) -> None:
        """Initialize instance."""
        self.callee: list[Node] = []

    def add_callee(self, node: Node) -> None:
        """Add a callee to the current node.

        Parameters
        ----------
        node : Node
            The callee node.
        """
        self.callee.append(node)

    def has_callee(self) -> bool:
        """Check if the current node has callees.

        Returns
        -------
        bool
            Return False if there are no callees, otherwise True.
        """
        return bool(self.callee)


class CallGraph(Generic[Node]):
    """This is the generic class for creating a call graph."""

    def __init__(self, root: Node, repo_path: str) -> None:
        """Initialize instance.

        Parameters
        ----------
        root : Node
            The root call graph node.
        repo_path : str
            The path to the repo.
        """
        self.root = root
        self.repo_path = repo_path

    def get_root(self) -> Node:
        """Get the root node in the call graph.

        Returns
        -------
        Node
            The root node.
        """
        return self.root

    def bfs(self) -> Iterable[Node]:
        """Traverse the call graph in breadth first search order.

        Yields
        ------
        Node
            The traversed nodes.
        """
        queue = []
        queue.extend(self.root.callee)
        visited = []
        while queue:
            node = queue.pop(0)
            if node not in visited:
                queue.extend(node.callee)
                visited.append(node)
                yield node
