# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This package contains the provenance tools for software components."""

from dataclasses import dataclass

from macaron.slsa_analyzer.provenance.intoto import InTotoPayload


@dataclass(frozen=True)
class ProvenanceAsset:
    """This class exists to hold a provenance payload with the original asset's name and URL."""

    payload: InTotoPayload
    name: str
    url: str
