# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module compares the contents of two JSON find_source files and reports on their equality."""

import logging

logger: logging.Logger = logging.getLogger(__name__)

# Set logging debug level.
logger.setLevel(logging.DEBUG)


def compare_find_source_reports(first: dict, second: dict) -> int:
    """Compare the content of the two report files."""
    result = 0

    for key in first:
        if key not in second:
            logger.error("Key mismatch: %s -> MISSING", key)
            result += 1

    for key in second:
        if key not in first:
            logger.error("Key mismatch: MISSING -> %s", key)
            result += 1

    for key in first:
        if key not in second:
            continue
        if first[key] != second[key]:
            logger.error("Value mismatch for key '%s': '%s' != '%s'", key, first[key], second[key])
            result += 1

    return result
