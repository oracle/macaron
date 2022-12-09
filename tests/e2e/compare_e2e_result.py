#!/usr/bin/env python3

# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module checks the result JSON files against the expected outputs."""

import json
import logging
import sys

logger: logging.Logger = logging.getLogger(__name__)

# Set logging debug level.
logger.setLevel(logging.DEBUG)


def compare_check_results(result: dict, expected: dict) -> int:
    """Compare the content of the target.checks section."""
    fail_count = 0

    # Compare summary
    for key, exp_val in expected["summary"].items():
        if exp_val != result["summary"].get(key):
            logger.error(
                "Compare failed at field ['%s']. EXPECT %s, GOT %s",
                key,
                exp_val,
                result["summary"][key],
            )
            fail_count += 1

    # Compare check results
    res_sorted_reqs = sorted(result["results"], key=lambda item: item["check_id"])
    exp_sorted_reqs = sorted(expected["results"], key=lambda item: item["check_id"])

    if len(res_sorted_reqs) < len(exp_sorted_reqs):
        for req in exp_sorted_reqs[len(res_sorted_reqs) :]:
            logger.error(
                "Check %s is missing in the result output.",
                req["check_id"],
            )
            fail_count += 1

    for index, res_req in enumerate(res_sorted_reqs):
        if index >= len(exp_sorted_reqs):
            for req in res_sorted_reqs[index:]:
                logger.error(
                    "Check %s does not exist in the expected output.",
                    req["check_id"],
                )
            break

        exp_req = exp_sorted_reqs[index]

        # For each requirement the "justification" can be nondeterministic
        # if it contains a path to a file, so we remove it.
        res_req["justification"] = exp_req["justification"] = ""

        if res_req["check_id"] == exp_req["check_id"]:
            for key, value in exp_req.items():
                if res_req[key] != value:
                    fail_count += 1
                    logger.error(
                        (
                            "Check id = %s, key = %s: value = %s in "
                            "the result does not match value "
                            "= %s in the expected output."
                        ),
                        res_req["check_id"],
                        key,
                        res_req[key],
                        value,
                    )
        else:
            fail_count += 1
            logger.error(
                "Requirement %s does not match %s in the expected output.",
                res_req["check_id"],
                exp_req["check_id"],
            )

    return fail_count


def compare_target_info(result: dict, expected: dict) -> int:
    """Compare the content of the target.info section"""
    # Remove nondeterministic fields
    result["local_cloned_path"] = expected["local_cloned_path"] = ""
    result["commit_date"] = expected["commit_date"] = ""

    fail_count = 0

    # Iterate through elements in the JSON dictionary
    for key, exp_item in expected.items():
        result_item = result.get(key)

        if exp_item != result_item:
            logger.error(
                "Compare failed at field %s. EXPECT %s, GOT %s",
                key,
                exp_item,
                result_item,
            )
            fail_count += 1

    return fail_count


def compare_result_json(result_path: str, expect_path: str) -> int:
    """Compare the content of the result JSON file against the expected result."""
    with open(expect_path, encoding="utf-8") as expect_file, open(result_path, encoding="utf-8") as result_file:
        result: dict = json.load(result_file)
        expected: dict = json.load(expect_file)
        fail_count = 0
        fail_count += compare_target_info(result["target"]["info"], expected["target"]["info"])
        fail_count += compare_check_results(result["target"]["checks"], expected["target"]["checks"])
        return fail_count


def main() -> None:
    """Compare the resultJSON files with expected output.

    The first argument is the directory that stored the results we want to check.
    The second argument is the directory to expected results.

    This script will compare all JSON files with identical names from
    those two directories.
    """
    result_path = sys.argv[1]
    expect_path = sys.argv[2]

    fail_count = compare_result_json(result_path, expect_path)

    if fail_count > 0:
        raise ValueError(f"{fail_count} JSON results did not match the expected output.")


if __name__ == "__main__":
    main()
