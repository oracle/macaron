# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This file defines the heuristic-analysis result type enum, and function to modify result."""

from enum import Enum


class HeuristicResult(Enum):
    """Result type.

    PASS: Not suspicious
    FAIL: Suspicious
    SKIP: Metadata miss
    """

    PASS = "PASS"  # nosec
    FAIL = "FAIL"  # nosec
    SKIP = "SKIP"  # nosec
