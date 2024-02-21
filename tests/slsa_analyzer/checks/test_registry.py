# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Registry class."""

import os
import queue
from graphlib import TopologicalSorter
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis.strategies import SearchStrategy, binary, booleans, integers, lists, none, one_of, text, tuples

from macaron.config.defaults import load_defaults
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType
from macaron.slsa_analyzer.registry import Registry


class MockCheck(BaseCheck):
    """BaseCheck with no-op impl for abstract method"""

    def run_check(self, ctx: AnalyzeContext) -> CheckResultData:
        return CheckResultData(justification=[], result_tables=[], result_type=CheckResultType.UNKNOWN)


# pylint: disable=protected-access
@pytest.fixture(name="check_registry")
def check_registry_fixture() -> Registry:
    """Return a registry instance with sample checks registered.

    Returns
    -------
    Registry
        The sample registry instance.
    """
    # Refresh Registry static variables before each test case
    Registry._all_checks_mapping = {}
    Registry._check_relationships_mapping = {}
    Registry._graph = TopologicalSorter()
    Registry._is_graph_ready = False

    registry = Registry()
    registry.register(BaseCheck("mcn_a_1", "Depend on b", [("mcn_b_1", CheckResultType.PASSED)]))  # type: ignore
    registry.register(BaseCheck("mcn_b_1", "Depend on c", [("mcn_c_1", CheckResultType.PASSED)]))  # type: ignore
    registry.register(BaseCheck("mcn_c_1", "Depend on d", [("mcn_d_1", CheckResultType.PASSED)]))  # type: ignore
    registry.register(BaseCheck("mcn_d_1", "Depend on e", [("mcn_e_1", CheckResultType.PASSED)]))  # type: ignore
    registry.register(BaseCheck("mcn_e_1", "Have no parent", []))  # type: ignore
    registry.register(BaseCheck("mcn_f_1", "Depend on c", [("mcn_c_1", CheckResultType.FAILED)]))  # type: ignore
    registry.register(BaseCheck("mcn_g_1", "Depend on h", [("mcn_h_1", CheckResultType.FAILED)]))  # type: ignore
    registry.register(BaseCheck("mcn_h_1", "Depend on i", [("mcn_i_1", CheckResultType.FAILED)]))  # type: ignore
    registry.register(BaseCheck("mcn_i_1", "Have no parent", []))  # type: ignore
    return registry


# pylint: disable=protected-access
class TestRegistry(TestCase):
    """This class tests the Registry module."""

    REGISTRY = Registry()

    def setUp(self) -> None:
        # Refresh Registry static variables before each test case
        Registry._all_checks_mapping = {}
        Registry._check_relationships_mapping = {}
        Registry._graph = TopologicalSorter()
        Registry._is_graph_ready = False

    def test_exit_on_duplicated(self) -> None:
        """Test registering a duplicated check_id Check."""
        with self.assertRaises(SystemExit):
            self.REGISTRY.register(MockCheck("mcn_duplicated_check_1", ""))
            self.REGISTRY.register(MockCheck("mcn_duplicated_check_1", ""))

    def test_exit_on_empty_check_id(self) -> None:
        """Test registering an empty check_id Check."""
        with self.assertRaises(SystemExit):
            self.REGISTRY.register(MockCheck("", ""))

    @given(one_of(none(), text(), integers(), tuples(), binary(), booleans()))
    def test_exit_on_invalid_registered_check(self, check: SearchStrategy) -> None:
        """Test registering an invalid Check."""
        with self.assertRaises(SystemExit):
            self.REGISTRY.register(check)  # type: ignore

    def test_add_successfully(self) -> None:
        """Test registering a Check correctly."""
        self.REGISTRY.register(MockCheck("mcn_correct_check_1", "This check is a correct Check."))
        assert self.REGISTRY.get_all_checks_mapping().get("mcn_correct_check_1")

    def test_exit_on_registering_undefined_check(self) -> None:
        """Test registering a check which Macaron cannot resolve its module."""
        with patch("inspect.getmodule", return_value=False):
            with self.assertRaises(SystemExit):
                self.REGISTRY.register(MockCheck("mcn_undefined_check_1", "This check is an undefined Check."))

    @given(one_of(none(), text(), integers(), tuples(), binary(), booleans()))
    def test_exit_on_invalid_check_relationship(self, relationship: SearchStrategy) -> None:
        """Test registering a check with invalid parent status definition."""
        with self.assertRaises(SystemExit):
            check = MockCheck(
                "mcn_invalid_status_1", "Invalid_status_check_should_exit", [relationship]  # type: ignore
            )
            self.REGISTRY.register(check)

    def test_add_relationship_entry(self) -> None:
        """Test adding a check relationship entry."""
        # Adding successfully
        self.REGISTRY.register(MockCheck("mcn_a_1", "Parent", []))
        self.REGISTRY.register(MockCheck("mcn_b_1", "Child1", [("mcn_a_1", CheckResultType.PASSED)]))
        self.REGISTRY.register(
            MockCheck(
                "mcn_c_1",
                "Child2",
                [
                    ("mcn_b_1", CheckResultType.PASSED),
                    ("mcn_a_1", CheckResultType.FAILED),
                ],
            )
        )
        self.REGISTRY.register(MockCheck("mcn_d_1", "Stand-alone", []))
        assert self.REGISTRY.get_all_checks_relationships() == {
            "mcn_a_1": {
                "mcn_b_1": CheckResultType.PASSED,
                "mcn_c_1": CheckResultType.FAILED,
            },
            "mcn_b_1": {"mcn_c_1": CheckResultType.PASSED},
            "mcn_d_1": {},
        }

        # Cannot add a check that depends on itself
        with self.assertRaises(SystemExit):
            self.REGISTRY.register(MockCheck("mcn_e_1", "Self-dependent-check", [("mcn_e_1", CheckResultType.PASSED)]))

        # Add a check with duplicated relationships
        with self.assertRaises(SystemExit):
            self.REGISTRY.register(
                MockCheck(
                    "mcn_f_1",
                    "Existing-relationship",
                    [
                        ("mcn_c_1", CheckResultType.PASSED),
                        ("mcn_c_1", CheckResultType.FAILED),
                    ],
                )
            )

    @given(
        lists(
            one_of(none(), text(), integers(), tuples(), binary(), booleans()),
            min_size=1,  # To ensure at least one invalid req is validated
        )
    )
    def test_exit_on_invalid_eval_reqs(self, eval_reqs: SearchStrategy) -> None:
        """Test registering a check with invalid eval reqs definition."""
        with self.assertRaises(SystemExit):
            check = MockCheck("mcn_invalid_eval_reqs_1", "Invalid_eval_reqs_should_exit", [], eval_reqs)  # type: ignore
            self.REGISTRY.register(check)

    @given(
        lists(
            one_of(none(), text(), integers(), tuples(), binary(), booleans()),
            min_size=1,
        )
    )
    def test_exit_on_invalid_status_on_skipped(self, status_on_skipped: SearchStrategy) -> None:
        """Test registering a check with invalid status_on_skipped instance variable."""
        with self.assertRaises(SystemExit):
            check = MockCheck(
                "mcn_invalid_eval_reqs_1", "Invalid_status_on_skipped", [], [], status_on_skipped  # type: ignore
            )
            self.REGISTRY.register(check)

    def test_add_graph_node_after_prepare(self) -> None:
        """Test calling Registry._add_node after calling prepare on the graph."""
        assert self.REGISTRY._add_node(MockCheck("mcn_before_1", "Check_registered_before_prepare", [], []))

        Registry._graph.prepare()
        Registry._is_graph_ready = True
        assert not self.REGISTRY._add_node(MockCheck("mcn_after_1", "Check_registered_after_prepare", [], []))

    def test_circular_dependencies(self) -> None:
        """Test registering checks with circular dependencies."""
        self.REGISTRY.register(MockCheck("mcn_a_1", "Depend_on_b", [("mcn_b_1", CheckResultType.PASSED)], []))

        self.REGISTRY.register(MockCheck("mcn_b_1", "Depend_on_c", [("mcn_c_1", CheckResultType.PASSED)], []))

        self.REGISTRY.register(MockCheck("mcn_c_1", "Depend_on_a", [("mcn_a_1", CheckResultType.PASSED)], []))

        assert not self.REGISTRY.prepare()

    def test_running_with_no_checks(self) -> None:
        """Test running the analysis with no check."""
        # The all_checks_mapping is empty due to
        # the setUp method.
        assert not self.REGISTRY.prepare()

    def test_running_with_no_runners(self) -> None:
        """Test running the analysis with no runners in the Registry."""
        self.REGISTRY.runners = []
        self.REGISTRY.runner_queue = queue.Queue()
        assert not self.REGISTRY.prepare()

    def test_prepare_successfully(self) -> None:
        """Test registry is prepared successfully and ready for the analysis."""
        self.REGISTRY.register(MockCheck("mcn_correct_check_1", "This check is a correct Check."))
        # For the prepare method to complete successfully,
        # the registry must have at least one check registered,
        # at least one runner initialized and no check circular
        # dependencies.
        assert Registry._all_checks_mapping
        assert self.REGISTRY.runners
        assert self.REGISTRY.prepare()

    def test_validate_check_id_format(self) -> None:
        """Test the validate check id format method."""
        valid_ids = ["mcn_some_thing_1", "mcn_some_1"]
        invalid_ids = [
            "",
            "^",
            "id_check",
            "mcn_CAPITAL_1",
            "mcn__1",
            "mcn_1",
            "mcn_1_",
            "mcn_has_no_number_",
            "mcn_has_no_number",
        ]

        assert all(Registry._validate_check_id_format(check_id) for check_id in valid_ids)
        assert all(not Registry._validate_check_id_format(check_id) for check_id in invalid_ids)


@pytest.mark.parametrize(
    ("ex_pats", "in_pats", "final_checks"),
    [
        (
            [],
            ["*"],
            ["mcn_a_1", "mcn_b_1", "mcn_c_1", "mcn_d_1", "mcn_e_1", "mcn_f_1", "mcn_g_1", "mcn_h_1", "mcn_i_1"],
        ),
        (
            [],
            ["*", "*"],
            ["mcn_a_1", "mcn_b_1", "mcn_c_1", "mcn_d_1", "mcn_e_1", "mcn_f_1", "mcn_g_1", "mcn_h_1", "mcn_i_1"],
        ),
        (
            [],
            ["mcn_?_1"],
            ["mcn_a_1", "mcn_b_1", "mcn_c_1", "mcn_d_1", "mcn_e_1", "mcn_f_1", "mcn_g_1", "mcn_h_1", "mcn_i_1"],
        ),
        (
            [],
            ["mcn_[cf]_1"],
            ["mcn_c_1", "mcn_f_1", "mcn_d_1", "mcn_e_1"],
        ),
        ([], [], []),
        (["*"], [], []),
        (["*"], ["*"], []),
        (["*", "*", "*"], ["*", "*"], []),
        (
            [],
            ["mcn_a_1", "mcn_b_1", "mcn_c_1", "mcn_d_1", "mcn_e_1", "mcn_f_1", "mcn_g_1", "mcn_h_1", "mcn_i_1"],
            ["mcn_a_1", "mcn_b_1", "mcn_c_1", "mcn_d_1", "mcn_e_1", "mcn_f_1", "mcn_g_1", "mcn_h_1", "mcn_i_1"],
        ),
        (["mcn_c_1"], ["*"], ["mcn_d_1", "mcn_e_1", "mcn_g_1", "mcn_h_1", "mcn_i_1"]),
        ([], ["mcn_c_1"], ["mcn_c_1", "mcn_d_1", "mcn_e_1"]),
        (["mcn_d_1"], ["mcn_c_1"], ["mcn_e_1"]),
        (["mcn_*"], ["*"], []),
    ],
)
def test_get_final_checks(
    check_registry: Registry, ex_pats: list[str], in_pats: list[str], final_checks: list[str]
) -> None:
    """This method tests the get_final_checks method."""
    assert sorted(check_registry.get_final_checks(ex_pats=ex_pats, in_pats=in_pats)) == sorted(final_checks)


@pytest.mark.parametrize(
    ("check_id", "children"),
    [
        (
            "mcn_a_1",
            [],
        ),
        (
            "mcn_b_1",
            ["mcn_a_1"],
        ),
        (
            "mcn_c_1",
            ["mcn_f_1", "mcn_b_1"],
        ),
    ],
)
def test_get_children(check_registry: Registry, check_id: str, children: set[str]) -> None:
    """This method test the get_children method."""
    result = sorted(check_registry.get_children(check_id))
    expect = sorted(children)
    assert result == expect


@pytest.mark.parametrize(
    ("check_id", "parent"),
    [
        (
            "mcn_a_1",
            ["mcn_b_1"],
        ),
        (
            "mcn_b_1",
            ["mcn_c_1"],
        ),
        (
            "mcn_e_1",
            [],
        ),
    ],
)
def test_get_parents(check_registry: Registry, check_id: str, parent: set[str]) -> None:
    """This method test the get_children method."""
    result = sorted(check_registry.get_parents(check_id))
    expect = sorted(parent)
    assert result == expect


@pytest.mark.parametrize(
    ("user_config_input"),
    [
        pytest.param(
            """
            [analysis.checks]
            exclude = *
            include = *
            """,
            id="Exclude every checks",
        ),
        pytest.param(
            """
            [analysis.checks]
            exclude =
            include =
            """,
            id="No check is included",
        ),
        pytest.param(
            """
            [analysis.checks]
            exclude = *
            include =
            """,
            id="No check is included and no check is included",
        ),
    ],
)
def test_invalid_exclude_include_from_defaults(
    tmp_path: Path,
    check_registry: Registry,
    user_config_input: str,
) -> None:
    """Test Registry.prepare on invalid exclude/include check config.

    An invalid exclude/include check config means that it results in no run check.
    """
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)

    load_defaults(user_config_path)
    assert not check_registry.prepare()


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
        Registry.get_transitive_closure(
            node=start_node,
            get_successors=get_successors,
        )
    ) == sorted(expected)
