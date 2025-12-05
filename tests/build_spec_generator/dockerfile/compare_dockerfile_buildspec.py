# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Script to compare a generated dockerfile buildspec."""

import argparse
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logging.basicConfig(format="[%(filename)s:%(lineno)s %(tag)s] %(message)s")


def log_with_tag(tag: str) -> Callable[[str], None]:
    """Generate a log function that prints the name of the file and a tag at the beginning of each line."""

    def log_fn(msg: str) -> None:
        logger.info(msg, extra={"tag": tag})

    return log_fn


log_info = log_with_tag("INFO")
log_err = log_with_tag("ERROR")
log_passed = log_with_tag("PASSED")
log_failed = log_with_tag("FAILED")


def log_diff(result: str, expected: str) -> None:
    """Pretty-print the diff of two strings."""
    output = [
        *("----  Result  ---", result),
        *("---- Expected ---", expected),
        "-----------------",
    ]
    log_info("\n".join(output))


def main() -> int:
    """Compare a Macaron generated dockerfile buildspec.

    Returns
    -------
    int
        0 if the generated dockerfile matches the expected output, or non-zero otherwise.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dockerfile", help="the result dockerfile buildspec")
    parser.add_argument("expected_dockerfile_buildspec", help="the expected buildspec dockerfile")
    args = parser.parse_args()

    # Load both files
    with open(args.result_dockerfile, encoding="utf-8") as file:
        buildspec = normalize(file.read())

    with open(args.expected_dockerfile_buildspec, encoding="utf-8") as file:
        expected_buildspec = normalize(file.read())

    log_info(
        f"Comparing the dockerfile buildspec {args.result_dockerfile} with the expected "
        + "output dockerfile {args.expected_dockerfile_buildspec}"
    )

    # Compare the files
    return compare(buildspec, expected_buildspec)


def normalize(contents: str) -> list[str]:
    """Convert string of file contents to list of its non-empty lines"""
    return [line.strip() for line in contents.splitlines() if line.strip()]


def compare(buildspec: list[str], expected_buildspec: list[str]) -> int:
    """Compare the lines in the two files directly.

    Early return when an unexpected difference is found. If the lengths
    mismatch, but the first safe_index_max lines are the same, print
    the missing/extra lines.

    Returns
    -------
    int
        0 if the generated dockerfile matches the expected output, or non-zero otherwise.
    """
    safe_index_max = min(len(buildspec), len(expected_buildspec))
    for index in range(safe_index_max):
        if buildspec[index] != expected_buildspec[index]:
            # Log error
            log_err("Mismatch found:")
            # Log diff
            log_diff(buildspec[index], expected_buildspec[index])
            return 1
    if safe_index_max < len(expected_buildspec):
        log_err("Mismatch found: result is missing trailing lines")
        log_diff("", "\n".join(expected_buildspec[safe_index_max:]))
        return 1
    if safe_index_max < len(buildspec):
        log_err("Mismatch found: result has extra trailing lines")
        log_diff("\n".join(buildspec[safe_index_max:]), "")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
