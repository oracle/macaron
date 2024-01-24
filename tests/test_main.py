# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Simple tests for the main method."""

from importlib import metadata as importlib_metadata

import pytest

from macaron.__main__ import main


@pytest.mark.parametrize(
    ("flag"),
    [
        "--version",
        "-V",
    ],
)
def test_version(capsys: pytest.CaptureFixture, flag: str) -> None:
    """Test the ``--version/-V`` flag.

    Stdout format should be correct and exit code should be 0.
    """
    with pytest.raises(SystemExit) as exc_info:
        main([flag])
    out, err = capsys.readouterr()

    # Test that we are indeed outputting Macaron version.
    assert out == f"macaron {importlib_metadata.version('macaron')}\n"
    assert err == ""
    assert exc_info.value.code == 0
