# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This script checks the policy engine report against expected results."""
import json
import logging
import sys
from collections import Counter

logger: logging.Logger = logging.getLogger(__name__)

# Set logging debug level.
logger.setLevel(logging.DEBUG)


def check_policies(results: list, expectations: list) -> bool:
    """
    Compare result policies against expected policies.

    Parameters
    ----------
    results: list
        The result policy list.
    expectations:
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
    fail_count = 0
    if len(results) == len(expectations):
        # Iterate through the rows returned by the policy engine.
        for index, exp in enumerate(expectations):
            res = results[index]
            if (fails := abs(len(res) - len(exp))) > 0:
                fail_count += fails
                continue
            # Do not check the first element, which is the primary key.
            c_fail = Counter(exp[1:])
            c_fail.subtract(Counter(res[1:]))
            if (fails := len([value for value in c_fail.values() if value != 0])) > 0:
                fail_count += fails
    else:
        fail_count += abs(len(results) - len(expectations))

    if fail_count > 0:
        raise ValueError(
            f"Results do not match in {fail_count} item(s): Result is {results} but expected {expectations}"
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
                logger.error("failed_policies: %s", error)

            try:
                check_policies(result["passed_policies"], expected["passed_policies"])
            except ValueError as error:
                return_code = 1
                logger.error("passed_policies: %s", error)

            try:
                check_policies(result["component_violates_policy"], expected["component_violates_policy"])
            except ValueError as error:
                return_code = 1
                logger.error("component_violates_policy: %s", error)

            try:
                check_policies(result["component_satisfies_policy"], expected["component_satisfies_policy"])
            except ValueError as error:
                return_code = 1
                logger.error("component_satisfies_policy: %s", error)

    except FileNotFoundError as error:
        logger.error(error)
        return_code = 1

    return return_code


if __name__ == "__main__":
    sys.exit(main())
