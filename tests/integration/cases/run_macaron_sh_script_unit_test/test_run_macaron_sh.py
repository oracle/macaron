# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the ``run_macaron.sh`` script."""

import os
import subprocess  # nosec B404
import sys
import tempfile
from collections import namedtuple

TestCase = namedtuple("TestCase", ["name", "script_args", "expected_macaron_args"])


def run_test_case(
    test_case: TestCase,
    env: dict[str, str],
) -> int:
    """Run a test case in an environment with variables defined by `env` and return the exit code."""
    exit_code = 0

    name, script_args, expected_macaron_args = test_case
    print(f"test_macaron_command[{name}]:", end=" ")

    result = subprocess.run(
        [  # nosec B603
            "./output/run_macaron.sh",
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
        return exit_code

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


def test_macaron_command_help() -> int:
    """Test if the ``macaron`` command in the container receives the correct arguments."""
    test_cases = [
        TestCase(
            name="'-h' as main argument",
            script_args=["-h"],
            expected_macaron_args=["-h"],
        ),
        TestCase(
            name="'-h' as action argument for 'dump-defaults'",
            script_args=["dump-defaults", "-h"],
            expected_macaron_args=["dump-defaults", "-h"],
        ),
        TestCase(
            name="'-h' as action argument for 'verify-policy'",
            script_args=["verify-policy", "-h"],
            expected_macaron_args=["verify-policy", "-h"],
        ),
    ]

    env = dict(os.environ)
    env["MCN_DEBUG_ARGS"] = "1"

    for case in test_cases:
        exit_code = run_test_case(case, env)

    return exit_code


def test_macaron_command_no_home_m2_on_host() -> int:
    """Test if the ``macaron`` command in the container receives the correct arguments."""
    test_cases = [
        TestCase(
            name="no --local-maven-repo and host $HOME/.m2 is not available",
            script_args=["analyze"],
            expected_macaron_args=["analyze"],
        ),
    ]

    env = dict(os.environ)
    env["MCN_DEBUG_ARGS"] = "1"
    # We mimick the behavior of $HOME/.m2 not available by making $HOME pointing to a directory that doesn't exist.
    env["HOME"] = "./non_exist_dir"

    exit_code = 0
    for case in test_cases:
        exit_code = run_test_case(case, env)

    return exit_code


def test_macaron_command_host_home_m2_available() -> int:
    """Test if the ``macaron`` command in the container receives the correct arguments."""
    test_cases = [
        TestCase(
            name="no --local-maven-repo provided by the user and host $HOME/.m2 is available",
            script_args=["analyze"],
            expected_macaron_args=["analyze", "--local-maven-repo", "/home/macaron/analyze_local_maven_repo_readonly"],
        ),
    ]

    env = dict(os.environ)
    env["MCN_DEBUG_ARGS"] = "1"
    exit_code = 0

    with tempfile.TemporaryDirectory() as temp_dir:
        # We create a temp dir with a .m2 directory and point $HOME to it.
        # This .m2 directory contains an empty `repository` directory.
        os.mkdir(os.path.join(temp_dir, ".m2"))
        os.mkdir(os.path.join(temp_dir, ".m2/repository"))
        env["HOME"] = temp_dir

        for case in test_cases:
            exit_code = run_test_case(case, env)

    return exit_code


def test_macaron_user_provide_valid_local_maven_repo() -> int:
    """Test if the ``macaron`` command in the container receives the correct arguments."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_cases = [
            TestCase(
                name="with --local-maven-repo pointing to an existing directory",
                script_args=["analyze", "--local-maven-repo", f"{temp_dir}"],
                expected_macaron_args=[
                    "analyze",
                    "--local-maven-repo",
                    "/home/macaron/analyze_local_maven_repo_readonly",
                ],
            ),
        ]

        env = dict(os.environ)
        env["MCN_DEBUG_ARGS"] = "1"
        exit_code = 0

        for case in test_cases:
            exit_code = run_test_case(case, env)

    return exit_code


def main() -> int:
    """Run all tests."""
    return (
        test_macaron_command_help()
        | test_macaron_command_no_home_m2_on_host()
        | test_macaron_command_host_home_m2_available()
        | test_macaron_user_provide_valid_local_maven_repo()
    )


if __name__ == "__main__":
    sys.exit(main())
