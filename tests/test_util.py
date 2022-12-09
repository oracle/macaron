# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module test the Util methods
"""

from unittest import TestCase
from unittest.mock import call, patch

from macaron import util


class TestUtil(TestCase):
    """
    This class provide tests for the util package.
    """

    def test_construct_query(self) -> None:
        """
        Test whether query is constructed properly
        """
        query = util.construct_query(
            {
                "q": "Some simple query language:java",
                "sort": "stars",
                "order": "desc",
            }
        )
        assert query == r"q=Some+simple+query+language%3Ajava&sort=stars&order=desc"

    # TODO: the copy_file_bulk method is essential, however, this test
    # need further works.
    def test_copy_file_bulk(self) -> None:
        """
        Test the copy file bulk method
        """
        src_path = "/src/path"
        target_path = "/target/path"

        # Testing making dir to store files
        with patch("macaron.util.copy_file") as mock_copy_file:
            with patch("os.makedirs") as mock_make_dirs:
                # Empty file list, it does nothing
                assert util.copy_file_bulk([], src_path, target_path)
                mock_copy_file.assert_not_called()
                mock_make_dirs.assert_not_called()

            with patch("os.makedirs") as mock_make_dirs:
                # Test creating the dirs for storing the file
                assert util.copy_file_bulk(["foo/file"], src_path, target_path)
                mock_make_dirs.assert_called_with("/target/path/foo", exist_ok=True)

        # Testing copy behaviors
        with patch("os.makedirs") as mock_make_dirs:
            # Test ignoring existed files
            with patch("os.path.exists", return_value=True):
                with patch("macaron.util.copy_file") as mock_copy_file:
                    assert util.copy_file_bulk(["file"], src_path, target_path)
                    mock_copy_file.assert_not_called()

            # Files not existed, perform the copy operation
            with patch("os.path.exists", return_value=False):
                # Test copying file successful
                with patch("macaron.util.copy_file", return_value=True) as mock_copy_file:
                    assert util.copy_file_bulk(["file"], src_path, target_path)

                # Test copying file unsuccessful
                with patch("macaron.util.copy_file", return_value=False) as mock_copy_file:
                    assert not util.copy_file_bulk(["file"], src_path, target_path)

                # Test copying multiple files
                with patch("macaron.util.copy_file", return_value=True) as mock_copy_file:
                    assert util.copy_file_bulk(["foo/file1", "foo/file2"], src_path, target_path)
                    mock_copy_file.assert_has_calls(
                        [
                            call("/src/path/foo/file1", "/target/path/foo/file1"),
                            call("/src/path/foo/file2", "/target/path/foo/file2"),
                        ]
                    )
