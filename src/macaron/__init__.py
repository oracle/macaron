# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module initializes the necessary components for the macaron package."""

import os

# The version of this package. There's no comprehensive, official list of other
# magic constants, so we stick with this one only for now. See also this conversation:
# https://stackoverflow.com/questions/38344848/is-there-a-comprehensive-table-of-pythons-magic-constants
__version__ = "0.0.0"

# The path to the Macaron package.
MACARON_PATH = os.path.dirname(os.path.abspath(__file__))
