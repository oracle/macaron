# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This script checks the dependency analysis results against the expected outputs.
"""

import json
import logging
import sys

logger: logging.Logger = logging.getLogger(__name__)

# Set logging debug level.
logger.setLevel(logging.DEBUG)


def main() -> None:
    """Compare the dependency analysis results with expected output."""
    with open(sys.argv[1], encoding="utf8") as res_file, open(sys.argv[2], encoding="utf8") as exp_file:
        result = json.load(res_file)
        expected = json.load(exp_file)
        fail_count = 0

        # Iterate through the elements to provide useful debug info.
        # We could use deepdiff library, but let's avoid adding a third-party dependency.
        result_sorted = sorted(result, key=lambda item: str(item["id"]))
        expected_sorted = sorted(expected, key=lambda item: str(item["id"]))

        if len(result_sorted) < len(expected_sorted):
            for dep in expected_sorted[len(result_sorted) :]:
                fail_count += 1
                logger.error("Dependency %s is missing in the result output.", dep["id"])

        for index, item1 in enumerate(result_sorted):
            if index >= len(expected_sorted):
                for dep in result_sorted[index:]:
                    fail_count += 1
                    logger.error(
                        "Dependency %s does not exist in the expected output.",
                        dep["id"],
                    )
                break
            item2 = expected_sorted[index]
            if item1["id"] == item2["id"]:
                # Remove the non-deterministic values.
                item1["note"] = item2["note"] = ""
                item1["available"] = item2["available"] = True
                for key, value in item1.items():
                    if item2[key] != value:
                        fail_count += 1
                        logger.error(
                            (
                                "id = %s, key = %s: value = %s in "
                                "the result does not match value "
                                "= %s in the expected output."
                            ),
                            item1["id"],
                            key,
                            value,
                            item2[key],
                        )
            else:
                fail_count += 1
                logger.error(
                    "Dependency %s does not match %s in the expected output.",
                    item1["id"],
                    item2["id"],
                )

        if fail_count > 0:
            raise ValueError(f"{fail_count} dependency analysis results did not match the expected output.")


if __name__ == "__main__":
    main()
