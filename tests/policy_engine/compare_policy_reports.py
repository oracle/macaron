#!/usr/bin/env python3

# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module checks the policy engine report against expected results."""
import json
import logging
import sys

logger: logging.Logger = logging.getLogger(__name__)

# Set logging debug level.
logger.setLevel(logging.DEBUG)


def check_policies(result: list, expected: list) -> bool:
    """
    Compare result policies against expected policies.

    Parameters
    ----------
    result: list
        The result policy list.
    expected:
        The expected policy list.

    Returns
    -------
    bool
        Returns True if successful.

    Raises
    ------
    ValueError
    """
    # If not empty, policy is always a list with one item.
    # For example, Datalog declaration for failed_policies is `failed_policies(policy_id: symbol)`.
    res = {policy[0] for policy in result if policy}
    exp = {policy[0] for policy in expected if policy}
    fail_count = 0
    if len(res) == len(exp):
        if (fails := len(res.difference(exp))) > 0:
            fail_count += fails
    else:
        fail_count += abs(len(res) - len(exp))

    if fail_count > 0:
        raise ValueError(
            f"Results do not match in {fail_count} item(s): Result is [{','.join(res)}] but expected [{','.join(exp)}]"
        )
    return True


def main() -> int:
    """Compare the policy engine results with expected output."""
    return_code = 0
    try:
        with open(sys.argv[1], encoding="utf8") as res_file, open(sys.argv[2], encoding="utf8") as exp_file:
            result = json.load(res_file)
            expected = json.load(exp_file)

            try:
                check_policies(result["failed_policies"], expected["failed_policies"])
            except ValueError as error:
                return_code = 1
                logger.error("Failed policies: %s", error)

            try:
                check_policies(result["passed_policies"], expected["passed_policies"])
            except ValueError as error:
                return_code = 1
                logger.error("Passed policies: %s", error)
    except FileNotFoundError as error:
        logger.error(error)
        return_code = 1

    return return_code


if __name__ == "__main__":
    sys.exit(main())
