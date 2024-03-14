# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the Runner module."""

from macaron.database.table_definitions import Analysis, Component, Repository
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType
from macaron.slsa_analyzer.registry import Registry

from ...macaron_testcase import MacaronTestCase


class EmptyCheck(BaseCheck):
    """An empty check to test the runners."""

    def __init__(
        self,
        check_id: str,
        should_return: CheckResultType,
        parent: list[tuple[str, CheckResultType]],
    ) -> None:
        """Initialize the instance.

        Parameters
        ----------
        check_id: str
            The id of the check

        should_return: CheckResultType
            The result status returned by this check

        parent: list[tuple[str, CheckResultType]]
            The list of parent checks that this check depends on.
        """
        super().__init__(check_id, "This is an empty check.", parent, [])
        self.should_return = should_return

    def run_check(self, ctx: AnalyzeContext) -> CheckResultData:
        return CheckResultData(result_tables=[], result_type=self.should_return)


class TestRunner(MacaronTestCase):
    """Test the check runner."""

    # pylint: disable=protected-access
    def test_runner(self) -> None:
        """Test the running process of Registry.

        This test uses EmptyCheck with pre-defined return value.
        """
        # Create a fresh registry
        registry = Registry()
        Registry._all_checks_mapping = {}
        Registry._check_relationships_mapping = {}

        # Register checks
        # The final graph should be:
        # (The annotation A ----> B means B depends on A
        # the label P means PASSED and F means FAILED.)
        #
        #     +---+       P      +---+
        #     | A |------------> | B |
        #     +---+              +---+
        #          -\  F      F /- |
        #            -\       /-   | F
        #              -\   /-     |
        #                /--       |
        #              /-  -\      V
        #     +---+  /-      -\  +---+
        #     | C |<-     P    ->| D |
        #     +---+ -----------> +---+
        #        \                 /
        #         \               /
        #        P \             /  F
        #           \           /
        #            \  +---+  /
        #             ->| E |<-
        #               +---+
        #
        # The pre-defined return status for all checks are:
        #   A: PASSED
        #   B: FAILED
        #   C: FAILED
        #   D: PASSED
        #   E: PASSED
        #
        # Therefore, the run-time order of checks is:
        #   A -> B -> C (E and D are skipped).
        registry.register(EmptyCheck("mcn_a_1", CheckResultType.PASSED, []))
        registry.register(EmptyCheck("mcn_b_1", CheckResultType.FAILED, [("mcn_a_1", CheckResultType.PASSED)]))
        registry.register(
            EmptyCheck(
                "mcn_d_1",
                CheckResultType.PASSED,
                [
                    ("mcn_b_1", CheckResultType.FAILED),
                    ("mcn_a_1", CheckResultType.FAILED),
                    ("mcn_c_1", CheckResultType.PASSED),
                ],
            )
        )
        registry.register(EmptyCheck("mcn_c_1", CheckResultType.FAILED, [("mcn_b_1", CheckResultType.FAILED)]))
        registry.register(
            EmptyCheck(
                "mcn_e_1",
                CheckResultType.PASSED,
                [("mcn_c_1", CheckResultType.PASSED), ("mcn_d_1", CheckResultType.FAILED)],
            )
        )

        assert registry.prepare()

        # The pre-defined checks do not use AnalyzeContext (for simplicity) so
        # we can create an empty AnalyzeContext instance.
        component = Component(
            purl="pkg:github.com/package-url/purl-spec@244fd47e07d1004f0aed9c",
            analysis=Analysis(),
            repository=Repository(complete_name="github.com/package-url/purl-spec", fs_path=""),
        )
        target = AnalyzeContext(component=component)
        results = registry.scan(target)

        assert results["mcn_e_1"].result.result_type == results["mcn_d_1"].result.result_type == CheckResultType.SKIPPED
