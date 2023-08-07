# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines asset classes.

Assets are essentially files published from some build.
"""

from typing import Protocol

from macaron.slsa_analyzer.asset import IsAsset
from macaron.util import JsonType


class IsProvenance(Protocol):
    """Interface of a provenance."""

    @property
    def asset(self) -> IsAsset:
        """Get the asset."""

    @property
    def payload(self) -> dict[str, JsonType]:
        """Get the JSON payload of the provenance, in in-toto format.

        This payload must be a JSON object at the top-level, hence the return type.
        """
