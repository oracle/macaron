# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements SLSA provenance abstractions."""

from typing import NamedTuple

from macaron.intoto import InTotoPayload
from macaron.slsa_analyzer.asset import AssetLocator


class SLSAProvenanceData(NamedTuple):
    """SLSA provenance data."""

    #: The provenance asset.
    asset: AssetLocator
    #: The provenance payload.
    payload: InTotoPayload
