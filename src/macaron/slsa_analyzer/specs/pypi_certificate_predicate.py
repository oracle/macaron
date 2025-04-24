# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for predicates derived from a PyPI attestation certificate."""


class PyPICertificatePredicate:
    """This class implements the PyPI certificate predicate."""

    @staticmethod
    def build_predicate(source_url: str, source_digest: str, build_workflow: str, invocation_url: str) -> dict:
        """Build a predicate using passed parameters."""
        return {
            "buildType": "pypi_certificate",
            "sourceUri": f"{source_url}",
            "sourceDigest": f"{source_digest}",
            "workflow": f"{build_workflow}",
            "invocationUrl": f"{invocation_url}",
        }
