# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Registry class."""

import queue
from graphlib import TopologicalSorter
from unittest import TestCase
from unittest.mock import patch

from hypothesis import given
from hypothesis.strategies import SearchStrategy, binary, booleans, integers, lists, none, one_of, text, tuples

from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.registry import Registry


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
            self.REGISTRY.register(BaseCheck("mcn_duplicated_check_1", ""))  # type: ignore
            self.REGISTRY.register(BaseCheck("mcn_duplicated_check_1", ""))  # type: ignore

    def test_exit_on_empty_check_id(self) -> None:
        """Test registering an empty check_id Check."""
        with self.assertRaises(SystemExit):
            self.REGISTRY.register(BaseCheck("", ""))  # type: ignore

    @given(one_of(none(), text(), integers(), tuples(), binary(), booleans()))
    def test_exit_on_invalid_registered_check(self, check: SearchStrategy) -> None:
        """Test registering an invalid Check."""
        with self.assertRaises(SystemExit):
            self.REGISTRY.register(check)  # type: ignore

    def test_add_successfully(self) -> None:
        """Test registering a Check correctly."""
        self.REGISTRY.register(BaseCheck("mcn_correct_check_1", "This check is a correct Check."))  # type: ignore
        assert self.REGISTRY.get_all_checks_mapping().get("mcn_correct_check_1")

    def test_exit_on_registering_undefined_check(self) -> None:
        """Test registering a check which Macaron cannot resolve its module."""
        with patch("inspect.getmodule", return_value=False):
            with self.assertRaises(SystemExit):
                self.REGISTRY.register(
                    BaseCheck("mcn_undefined_check_1", "This check is an undefined Check.")  # type: ignore
                )

    @given(one_of(none(), text(), integers(), tuples(), binary(), booleans()))
    def test_exit_on_invalid_check_relationship(self, relationship: SearchStrategy) -> None:
        """Test registering a check with invalid parent status definition."""
        with self.assertRaises(SystemExit):
            check = BaseCheck(
                "mcn_invalid_status_1", "Invalid_status_check_should_exit", [relationship]  # type: ignore
            )
            self.REGISTRY.register(check)

    def test_add_relationship_entry(self) -> None:
        """Test adding a check relationship entry."""
        # Adding successfully
        self.REGISTRY.register(BaseCheck("mcn_a_1", "Parent", []))  # type: ignore
        self.REGISTRY.register(BaseCheck("mcn_b_1", "Child1", [("mcn_a_1", CheckResultType.PASSED)]))  # type: ignore
        self.REGISTRY.register(
            BaseCheck(  # type: ignore
                "mcn_c_1",
                "Child2",
                [
                    ("mcn_b_1", CheckResultType.PASSED),
                    ("mcn_a_1", CheckResultType.FAILED),
                ],
            )
        )
        self.REGISTRY.register(BaseCheck("mcn_d_1", "Stand-alone", []))  # type: ignore
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
            self.REGISTRY.register(
                BaseCheck("mcn_e_1", "Self-dependent-check", [("mcn_e_1", CheckResultType.PASSED)])  # type: ignore
            )

        # Add a check with duplicated relationships
        with self.assertRaises(SystemExit):
            self.REGISTRY.register(
                BaseCheck(
                    "mcn_f_1",
                    "Existing-relationship",  # type: ignore
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
            check = BaseCheck("mcn_invalid_eval_reqs_1", "Invalid_eval_reqs_should_exit", [], eval_reqs)  # type: ignore
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
            check = BaseCheck(
                "mcn_invalid_eval_reqs_1", "Invalid_status_on_skipped", [], [], status_on_skipped  # type: ignore
            )
            self.REGISTRY.register(check)

    def test_add_graph_node_after_prepare(self) -> None:
        """Test calling Registry._add_node after calling prepare on the graph."""
        assert self.REGISTRY._add_node(
            BaseCheck("mcn_before_1", "Check_registered_before_prepare", [], [])  # type: ignore
        )

        Registry._graph.prepare()
        Registry._is_graph_ready = True
        assert not self.REGISTRY._add_node(
            BaseCheck("mcn_after_1", "Check_registered_after_prepare", [], [])  # type: ignore
        )

    def test_circular_dependencies(self) -> None:
        """Test registering checks with circular dependencies."""
        self.REGISTRY.register(
            BaseCheck("mcn_a_1", "Depend_on_b", [("mcn_b_1", CheckResultType.PASSED)], [])  # type: ignore
        )

        self.REGISTRY.register(
            BaseCheck("mcn_b_1", "Depend_on_c", [("mcn_c_1", CheckResultType.PASSED)], [])  # type: ignore
        )

        self.REGISTRY.register(
            BaseCheck("mcn_c_1", "Depend_on_a", [("mcn_a_1", CheckResultType.PASSED)], [])  # type: ignore
        )

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
        self.REGISTRY.register(BaseCheck("mcn_correct_check_1", "This check is a correct Check."))  # type: ignore
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
