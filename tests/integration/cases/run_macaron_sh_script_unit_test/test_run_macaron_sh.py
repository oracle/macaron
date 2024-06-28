# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the ``run_macaron.sh`` script."""

import os
import subprocess  # nosec
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
    env = dict(os.environ)
    env["MCN_DEBUG_ARGS"] = "1"

    for test_case in test_cases:
        name, script_args, expected_macaron_args = test_case
        print(f"test_macaron_command[{name}]:", end=" ")

        result = subprocess.run(
            [  # nosec
                "../../../../scripts/release_scripts/run_macaron.sh",
                *script_args,
            ],
            capture_output=True,
            env=env,
            check=False,
        )
        if result.returncode != 0:
            exit_code = 1
            print(f"FAILED with exit code {exit_code}")
            print("stderr:")
            print(result.stderr.decode("utf-8"))
            continue

        resulting_macaron_args = list(result.stderr.decode("utf-8").split())

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
