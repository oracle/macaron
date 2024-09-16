# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the DependencyAnalyzer.
"""

from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer
from tests.macaron_testcase import MacaronTestCase


class TestDependencyAnalyzer(MacaronTestCase):
    """Test the dependency analyzer functions."""

    def test_tool_valid(self) -> None:
        """Test the tool name and version is valid."""
        assert DependencyAnalyzer.tool_valid("cyclonedx:2.6.2") is False
        assert DependencyAnalyzer.tool_valid("cyclonedx-maven:2.6.2") is True
        assert DependencyAnalyzer.tool_valid("cyclonedx-maven:abc") is False
