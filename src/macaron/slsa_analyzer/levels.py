# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains classes that handle the analysis of each SLSA levels."""

from enum import Enum


class SLSALevels(Enum):
    """The enum for the SLSA level of each SLSA requirement.

    See Also: https://slsa.dev/spec.
    """

    LEVEL0 = "SLSA Level 0"
    LEVEL1 = "SLSA Level 1"
    LEVEL2 = "SLSA Level 2"
    LEVEL3 = "SLSA Level 3"
    LEVEL4 = "SLSA Level 4"
