# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module test the Util methods
"""
from collections.abc import Callable
from unittest import TestCase
from unittest.mock import call, patch

from pytest_httpserver import HTTPServer
from werkzeug import Request, Response

from macaron import util
from macaron.config.defaults import defaults
from macaron.util import send_get_http_raw


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


def _response_generator(target_value: int) -> Callable[[Request], Response]:
    """Return a generator with closure so a value can be tracked across multiple invocations."""
    value = 0

    def generator(request: Request) -> Response:  # pylint: disable=unused-argument
        """Add the next value as a header and adjust the status code based on the value."""
        nonlocal value, target_value
        value += 1
        response = Response()
        response.status_code = 403 if value <= (target_value + 1) else 200
        response.headers["X-VALUE"] = str(value)
        return response

    return generator


def test_get_http_failure(httpserver: HTTPServer) -> None:
    """Test get http operations when a 403 error code is received."""
    # Set up a localhost URL.
    mocked_url = httpserver.url_for("")

    # Retrieve the allowed number of retries on a failed request.
    target_value = defaults.getint("requests", "error_retries", fallback=5)

    # Create and assign the stateful handler.
    handler = _response_generator(target_value)
    httpserver.expect_request("").respond_with_handler(handler)

    # Assert the request fails and returns nothing.
    assert send_get_http_raw(mocked_url) is None

    # Test for a correct response after the expected number of retries and other requests (including this one).
    expected_value = target_value + 2
    response = send_get_http_raw(mocked_url)
    assert response
    assert "X-VALUE" in response.headers
    assert response.headers["X-VALUE"] == str(expected_value)
