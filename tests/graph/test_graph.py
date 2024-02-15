# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the test for the graph generic methods."""

import pytest

from macaron.graph.graph import get_transitive_closure


@pytest.mark.parametrize(
    ("start_node", "expected"),
    [
        ("A", ["A", "B", "C", "D", "E", "F", "H"]),
        ("B", ["B", "D"]),
        ("C", ["C", "F", "E", "H"]),
        ("D", ["D"]),
        ("E", ["E"]),
        ("F", ["F", "H"]),
        ("G", ["G", "C", "E", "F", "H"]),
        ("H", ["H"]),
    ],
)
def test_get_transitive_closure(start_node: str, expected: list[str]) -> None:
    """This method test get_transitive_closure method."""

    def get_successors(start: str) -> set[str]:
        match start:
            case "A":
                return {"B", "C"}
            case "B":
                return {"D"}
            case "C":
                return {"E", "F"}
            case "G":
                return {"C", "H"}
            case "F":
                return {"H"}
            case "D" | "E" | "H":
                return set()
            case _:
                return set()

    assert sorted(
        get_transitive_closure(
            node=start_node,
            get_successors=get_successors,
        )
    ) == sorted(expected)
