# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for predicates derived from a PyPI attestation certificate."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PyPICertificatePredicate:
    """This class implements the PyPI certificate predicate."""

    source_url: str

    source_digest: str

    build_workflow: str

    invocation_url: str

    def build_predicate(self) -> dict:
        """Build a predicate using passed parameters."""
        return {
            "buildType": "pypi_certificate",
            "sourceUri": f"{self.source_url}",
            "sourceDigest": f"{self.source_digest}",
            "workflow": f"{self.build_workflow}",
            "invocationUrl": f"{self.invocation_url}",
        }
