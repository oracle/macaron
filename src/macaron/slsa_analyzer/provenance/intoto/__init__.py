# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""In-toto provenance schemas and validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple, Protocol, TypeVar

from packageurl import PackageURL

from macaron.json_tools import JsonType
from macaron.slsa_analyzer.provenance.intoto import v01, v1
from macaron.slsa_analyzer.provenance.intoto.errors import ValidateInTotoPayloadError
from macaron.slsa_analyzer.provenance.intoto.v01 import InTotoV01Subject
from macaron.slsa_analyzer.provenance.intoto.v1 import InTotoV1ResourceDescriptor

# Type of an in-toto statement.
# This is currently either a v0.1 statement or v1 statement.
StatementT = TypeVar("StatementT", bound=Mapping)


class InTotoV01Payload(NamedTuple):
    """The provenance payload following in-toto v0.1 schema.

    The payload is a field within a DSSE envelope, having the type "Statement".

    In-toto spec (v0.1):
    - In-toto attestation layers:
    https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#attestation-spec
    - Envelope layer:
    https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#envelope
    - Statement layer:
    https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#statement
    """

    statement: v01.InTotoV01Statement


class InTotoV1Payload(NamedTuple):
    """The provenance payload following in-toto v1 schema.

    The payload is a field within a DSSE envelope, having the type "Statement".

    In-toto spec (v1):
    - In-toto attestation layers:
    https://github.com/in-toto/attestation/tree/main/spec/v1#specification-for-in-toto-attestation-layers
    - Envelope layer:
    https://github.com/in-toto/attestation/blob/main/spec/v1/envelope.md
    - Statement layer:
    https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md
    """

    statement: v1.InTotoV1Statement


# The payload is a field within a DSSE envelope, having the type "Statement".
#
# For more details, see the following pages in in-toto spec:
# - In-toto attestation layers: https://github.com/in-toto/attestation/tree/main/spec
# v0.1: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#attestation-spec
# v1  : https://github.com/in-toto/attestation/tree/main/spec/v1#specification-for-in-toto-attestation-layers
# - Envelope layer:
# v0.1: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#envelope
# v1  : https://github.com/in-toto/attestation/blob/main/spec/v1/envelope.md
# - Statement layer:
# v0.1: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#statement
# v1: https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md
InTotoPayload = InTotoV01Payload | InTotoV1Payload


def validate_intoto_payload(payload: dict[str, JsonType]) -> InTotoPayload:
    """Validate the schema of an in-toto provenance payload.

    Parameters
    ----------
    payload : dict[str, JsonType]
        The in-toto payload.

    Returns
    -------
    InTotoPayload
        The validated in-toto payload.

    Raises
    ------
    ValidateInTotoPayloadError
        When there is an error validating the payload.
    """
    type_ = payload.get("_type")
    if type_ is None:
        raise ValidateInTotoPayloadError(
            "The attribute '_type' of the in-toto statement is missing.",
        )
    if not isinstance(type_, str):
        raise ValidateInTotoPayloadError(
            "The value of attribute '_type' in the in-toto statement is invalid: expecting a string.",
        )

    if type_ == "https://in-toto.io/Statement/v0.1":
        # The type must always be this value for version v0.1.
        # See specification: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#statement.

        try:
            if v01.validate_intoto_statement(payload):
                return InTotoV01Payload(statement=payload)

            raise ValidateInTotoPayloadError("Unexpected error while validating the in-toto statement.")
        except ValidateInTotoPayloadError as error:
            raise error

    if type_ == "https://in-toto.io/Statement/v1":
        # The type must always be this value for version v1.
        # See specification: https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md.

        try:
            if v1.validate_intoto_statement(payload):
                return InTotoV1Payload(statement=payload)

            raise ValidateInTotoPayloadError("Unexpected error while validating the in-toto statement.")
        except ValidateInTotoPayloadError as error:
            raise error

    raise ValidateInTotoPayloadError("Invalid value for the attribute '_type' of the provenance payload.")


class ProvenanceSubjectPURLMatcher(Protocol):
    """Interface for a matcher that matches a PURL to a subject in the provenance."""

    @staticmethod
    def get_subject_in_provenance_matching_purl(
        provenance_payload: InTotoPayload,
        purl: PackageURL,
    ) -> InTotoV01Subject | InTotoV1ResourceDescriptor | None:
        """Obtain the subject in the provenance payload matching the given PackageURL.

        This function assumes there is only one such subject. If there are multiple
        such subjects, the first matching subject is returned. However, this should not
        happen since the PackageURL should be specific enough to identify a single subject.

        Parameters
        ----------
        provenance_payload : InTotoPayload
            The provenance payload.
        purl : PackageURL
            The PackageURL identifying the matching subject.

        Returns
        -------
        InTotoV01Subject | InTotoV1ResourceDescriptor | None
            The subject in the provenance matching the given PURL.
        """
