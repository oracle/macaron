# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This script compares 2 Reproducible Central Buildspec files."""

import logging
import os
import sys
from collections.abc import Callable

CompareFn = Callable[[object, object], bool]

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
log_failed = log_with_tag("FAILED")
log_passed = log_with_tag("PASSED")


def log_diff_str(name: str, result: str, expected: str) -> None:
    """Pretty-print the diff of two Python strings."""
    output = [
        f"'{name}'",
        *("----  Result  ---", f"{result}"),
        *("---- Expected ---", f"{expected}"),
        "-----------------",
    ]
    log_info("\n".join(output))


def skip_compare(_result: object, _expected: object) -> bool:
    """Return ``True`` always.

    This compare function is used when we want to skip comparing a field.
    """
    return True


def compare_rc_build_spec(
    result: dict[str, str],
    expected: dict[str, str],
    compare_fn_map: dict[str, CompareFn],
) -> bool:
    """Compare two dictionaries obatained from 2 Reproducible Central build spec.

    Parameters
    ----------
    result : dict[str, str]
        The result object.
    expected : dict[str, str]
        The expected object.
    compare_fn_map : str
        A map from field name to corresponding compare function.

    Returns
    -------
    bool
        ``True`` if the comparison is successful, ``False`` otherwise.
    """
    result_keys_only = result.keys() - expected.keys()
    expected_keys_only = expected.keys() - result.keys()

    equal = True

    if len(result_keys_only) > 0:
        log_err(f"Result has the following extraneous fields: {result_keys_only}")
        equal = False

    if len(expected_keys_only) > 0:
        log_err(f"Result does not contain these expected fields: {expected_keys_only}")
        equal = False

    common_keys = set(result.keys()).intersection(set(expected.keys()))

    for key in common_keys:
        if key in compare_fn_map:
            equal &= compare_fn_map[key](result, expected)
            continue

        if result[key] != expected[key]:
            log_err(f"Mismatch found in '{key}'")
            log_diff_str(key, result[key], expected[key])
            equal = False

    return equal


def extract_data_from_build_spec(build_spec_path: str) -> dict[str, str] | None:
    """Extract data from build spec."""
    original_build_spec_content = None
    try:
        with open(build_spec_path, encoding="utf-8") as build_spec_file:
            original_build_spec_content = build_spec_file.read()
    except OSError as error:
        log_err(f"Failed to read the Reproducible Central Buildspec file at {build_spec_path}. Error {error}.")
        return None

    build_spec_values: dict[str, str] = {}

    # A Reproducible Central buildspec is a valid bash script.
    # We use the following assumption to parse all key value mapping in a Reproducible Central buildspec.
    # 1. Each variable-value mapping has the form of
    #    <variable>=<value>
    # For example ``tool=mvn``
    # 2. If the first letter of a line is "#" we treat that line as a comment and ignore
    # it.
    for line in original_build_spec_content.splitlines():
        if not line or line.startswith("#"):
            continue

        variable, _, value = line.partition("=")
        # We allow defining a variable multiple times, where subsequent definition
        # override the previous one.
        build_spec_values[variable] = value

    return build_spec_values


def main() -> int:
    """Compare a Reproducible Central Buildspec file with an expected output."""
    result_path = sys.argv[1]
    expect_path = sys.argv[2]

    result_build_spec = extract_data_from_build_spec(result_path)
    expect_build_spec = extract_data_from_build_spec(expect_path)

    if not expect_build_spec:
        log_err(f"Failed to extract bash variables from expected Buildspec at {expect_path}.")
        return os.EX_USAGE

    if not result_build_spec:
        log_err(f"Failed to extract bash variables from result Buildspec at {result_build_spec}.")
        return os.EX_USAGE

    equal = compare_rc_build_spec(
        result=result_build_spec,
        expected=expect_build_spec,
        compare_fn_map={
            "buildinfo": skip_compare,
        },
    )

    if not equal:
        log_failed("The result RC Buildspec does not match the RC Buildspec.")
        return os.EX_DATAERR

    log_passed("The result RC Buildspec matches the RC Buildspec.")
    return os.EX_OK


if __name__ == "__main__":
    raise SystemExit(main())
