# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""In-toto provenance schemas and validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar

from macaron.slsa_analyzer.provenance.intoto import v01, v1
from macaron.slsa_analyzer.provenance.intoto.errors import ValidateInTotoPayloadError
from macaron.util import JsonType

StatementT = TypeVar("StatementT", bound=Mapping)
"""Type of an in-toto statement.

This is currently either a v0.1 statement or v1 statement.
"""


@dataclass(frozen=True)
class InTotoPayload(Generic[StatementT]):
    """The payload of an in-toto provenance."""

    statement: StatementT


class InTotoV01Payload(InTotoPayload[v01.InTotoStatement]):
    """The provenance payload following in-toto v0.1 schema.

    Specification: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#statement.
    """


class InTotoV1Payload(InTotoPayload[v1.InTotoStatement]):
    """The provenance payload following in-toto v1 schema.

    Specification: https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md.
    """


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
    _type = payload.get("_type")
    if _type is None:
        raise ValidateInTotoPayloadError(
            "The attribute '_type' of the in-toto statement is missing.",
        )
    if not isinstance(_type, str):
        raise ValidateInTotoPayloadError(
            "The value of attribute '_type' in the in-toto statement is invalid: expecting a string.",
        )

    if _type == "https://in-toto.io/Statement/v0.1":
        # The type must always be this value for version v0.1.
        # See specification: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#statement.

        try:
            if v01.validate_intoto_statement(payload):
                return InTotoV01Payload(statement=payload)

            raise ValidateInTotoPayloadError("Unexpected error while validating the in-toto statement.")
        except ValidateInTotoPayloadError as error:
            raise error

    # TODO: add support for version 1.

    raise ValidateInTotoPayloadError("Invalid value for the attribute '_type' of the provenance payload.")
