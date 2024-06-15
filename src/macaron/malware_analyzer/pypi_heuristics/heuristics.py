# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Define the heuristic enum."""

from enum import Enum


class HEURISTIC(Enum):
    """Seven heuristics."""

    EMPTY_PROJECT_LINK = "empty_project_link"
    UNREACHABLE_PROJECT_LINKS = "unreachable_project_links"
    ONE_RELEASE = "one_release"
    HIGH_RELEASE_FREQUENCY = "high_release_frequency"
    UNCHANGED_RELEASE = "unchanged_release"
    CLOSER_RELEASE_JOIN_DATE = "closer_release_join_date"
    SUSPICIOUS_SETUP = "suspicious_setup"
