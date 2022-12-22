# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for BaseCheck."""

from unittest import TestCase
from unittest.mock import MagicMock

from macaron.slsa_analyzer.checks.base_check import BaseCheck


class TestConfiguration(TestCase):
    """This class contains the tests for BaseCheck."""

    def test_raise_implementation_error(self) -> None:
        """Test raising errors if child class does not override abstract method(s)."""
        # pylint: disable=abstract-method
        class ChildCheck(BaseCheck):
            """This class is a child class that does not implement abstract methods in Base Check."""

            def __init__(self) -> None:
                super().__init__("Child check", "Child check without implemented abstract method(s).")

        with self.assertRaises(NotImplementedError):
            check = ChildCheck()  # type: ignore
            check.run_check(MagicMock(), MagicMock())
