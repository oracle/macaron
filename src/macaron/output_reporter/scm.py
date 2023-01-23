# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements datatypes to represent SCM results."""

from enum import Enum


class SCMStatus(str, Enum):
    """The status type of each analyzed repository."""

    AVAILABLE = "AVAILABLE"
    """The SCM url is available for this artifact."""
    MISSING_SCM = "MISSING REPO URL"
    """Cannot find the SCM url for this artifact."""
    DUPLICATED_SCM = "DUPLICATED REPO URL"
    """The SCM url is available but has been already analyzed for another artifact."""
    ANALYSIS_FAILED = "FAILED"
    """When the SCM is available but the analysis could not finish for this artifact."""
