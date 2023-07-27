# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines asset classes.

Assets are essentially files published from some build.
"""

from typing import Protocol


class Asset(Protocol):
    """Interface of an asset."""

    @property
    def name(self) -> str:
        """Get the name (file name) of the asset."""

    @property
    def url(self) -> str:
        """Get the url to the asset."""
