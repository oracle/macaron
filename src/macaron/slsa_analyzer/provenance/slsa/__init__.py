# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements SLSA provenance abstractions."""

from typing import NamedTuple

from macaron.slsa_analyzer.asset import AssetLocator
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload


class SLSAProvenanceData(NamedTuple):
    """SLSA provenance data."""

    #: The provenance asset.
    asset: AssetLocator
    #: The provenance payload.
    payload: InTotoPayload
