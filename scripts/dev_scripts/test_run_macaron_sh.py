#!/usr/bin/env python3

# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the ``run_macaron.sh`` script.

Note: this script is compatible with python >=3.6.
"""

import subprocess
import sys
from collections import namedtuple


def test_macaron_command() -> int:
    """Test if the ``macaron`` command in the container receives the correct arguments."""

    TestCase = namedtuple("TestCase", ["name", "script_args", "expected_macaron_args"])

    test_cases = [
        TestCase(
            name="'-h' as main argument",
            script_args=["-h"],
            expected_macaron_args=["-h"],
        ),
        TestCase(
            name="'-h' as action argument for 'analyze'",
            script_args=["analyze", "-h"],
            expected_macaron_args=["analyze", "-h"],
        ),
        TestCase(
            name="'-h' as action argument for 'verify-policy'",
            script_args=["verify-policy", "-h"],
            expected_macaron_args=["verify-policy", "-h"],
        ),
    ]

    exit_code = 0

    for test_case in test_cases:
        name, script_args, expected_macaron_args = test_case
        result = subprocess.run(
            [
                "scripts/release_scripts/run_macaron.sh",
                *script_args,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"MCN_DEBUG_ARGS": "1"},
            check=True,
        )
        resulting_macaron_args = list(result.stderr.decode("utf-8").split())

        print(f"test_macaron_command[{name}]:", end=" ")

        if resulting_macaron_args != expected_macaron_args:
            print("FAILED")
            print("  script args           : %s", str(script_args))
            print("  expected macaron args : %s", str(expected_macaron_args))
            print("  resulting macaron args: %s", str(resulting_macaron_args))
            exit_code = 1
        else:
            print("PASSED")

    return exit_code


def main() -> int:
    """Run all tests."""
    return test_macaron_command()


if __name__ == "__main__":
    sys.exit(main())
