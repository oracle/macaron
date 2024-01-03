# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines classes and interfaces related to provenances."""

from typing import Protocol

from macaron.intoto import InTotoPayload
from macaron.slsa_analyzer.asset import AssetLocator


class DownloadedProvenanceData(Protocol):
    """Interface of a provenance that has been downloaded (e.g. from a CI service or a package registry)."""

    @property
    def asset(self) -> AssetLocator:
        """Get the asset."""

    @property
    def payload(self) -> InTotoPayload:
        """Get the JSON payload of the provenance, in in-toto format.

        The payload is a field within a DSSE envelope, having the type "Statement".

        For more details, see the following pages in in-toto spec:

        In-toto attestation layers: https://github.com/in-toto/attestation/tree/main/spec
        - v0.1: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#attestation-spec
        - v1  : https://github.com/in-toto/attestation/tree/main/spec/v1#specification-for-in-toto-attestation-layers
        Envelope layer:
        - v0.1: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#envelope
        - v1  : https://github.com/in-toto/attestation/blob/main/spec/v1/envelope.md
        Statement layer:
        - v0.1: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#statement
        - v1: https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md
        """
