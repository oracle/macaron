# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the slsa_analyzer.Gh module."""

from pathlib import Path

from macaron.slsa_analyzer.analyzer import Analyzer

from ..macaron_testcase import MacaronTestCase


class TestAnalyzer(MacaronTestCase):
    """
    This class contains all the tests for the Analyzer
    """

    # Using the parent dir of this module as a valid start dir.
    PARENT_DIR = str(Path(__file__).parent)

    # pylint: disable=protected-access
    def test_resolve_local_path(self) -> None:
        """Test the resolve local path method."""
        # Test resolving a path outside of the start_dir
        assert not Analyzer._resolve_local_path(self.PARENT_DIR, "../")
        assert not Analyzer._resolve_local_path(self.PARENT_DIR, "./../")
        assert not Analyzer._resolve_local_path(self.PARENT_DIR, "../../../../../")

        # Test resolving a non-existing dir
        assert not Analyzer._resolve_local_path(self.PARENT_DIR, "./this-should-not-exist")

        # Test with invalid start_dir
        assert not Analyzer._resolve_local_path("non-existing-dir", "./")

        # Test resolve successfully
        assert Analyzer._resolve_local_path(self.PARENT_DIR, "./") == self.PARENT_DIR
        assert Analyzer._resolve_local_path(self.PARENT_DIR, "././././") == self.PARENT_DIR
