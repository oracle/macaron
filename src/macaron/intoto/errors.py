# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Error types related to in-toto attestations."""

from macaron.errors import MacaronError


class InTotoAttestationError(MacaronError):
    """The base error type for all in-toto related errors."""


class ValidateInTotoPayloadError(InTotoAttestationError):
    """Happens when there is an issue validating an in-toto payload, usually against a schema."""


class UnsupportedInTotoVersionError(InTotoAttestationError):
    """Happens when encountering an attestation under an unsupported in-toto version."""


class DecodeIntotoAttestationError(InTotoAttestationError):
    """Happens when there is an issue decoding the payload of an in-toto attestation."""


class LoadIntotoAttestationError(InTotoAttestationError):
    """Happens when there is an issue loading the payload of an in-toto attestation."""
