# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module handles in-toto version 0.1 attestations."""

from __future__ import annotations

from typing import TypedDict, TypeGuard

from macaron.slsa_analyzer.provenance.intoto.errors import ValidateInTotoPayloadError
from macaron.util import JsonType


class InTotoStatement(TypedDict):
    """An in-toto version 0.1 statement.

    This is the type of the payload in an in-toto version 0.1 attestation.
    Specification: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#statement.
    """

    _type: str
    subject: list[InTotoSubject]
    predicateType: str  # noqa: N815
    predicate: dict[str, JsonType] | None


class InTotoSubject(TypedDict):
    """An in-toto subject.

    Specification: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#statement.
    """

    name: str
    digest: dict[str, str]


def validate_intoto_statement(payload: dict[str, JsonType]) -> TypeGuard[InTotoStatement]:
    """Validate the statement of an in-toto attestation.

    Specification: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#statement.

    TODO: Consider using the in-toto-attestation package (https://github.com/in-toto/attestation/tree/main/python),
    which contains Python bindings for in-toto attestation.
    See issue: https://github.com/oracle/macaron/issues/426.

    Parameters
    ----------
    payload : dict[str, JsonType]
        The JSON statement after being base64-decoded.

    Returns
    -------
    TypeGuard[InTotoStatement]
        ``True`` if the subject element is valid, in which case its type is narrowed to an
        ``InTotoStatement``; ``False`` otherwise.

    Raises
    ------
    ValidateInTotoPayloadError
        When the payload does not follow the expected schema.
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

    subjects_payload = payload.get("subject")
    if subjects_payload is None:
        raise ValidateInTotoPayloadError(
            "The attribute 'subject' of the in-toto statement is missing.",
        )
    if not isinstance(subjects_payload, list):
        raise ValidateInTotoPayloadError(
            "The value of attribute 'subject' in the in-toto statement is invalid: expecting a list.",
        )

    for subject_json in subjects_payload:
        validate_intoto_subject(subject_json)

    predicate_type = payload.get("predicateType")
    if predicate_type is None:
        raise ValidateInTotoPayloadError(
            "The attribute 'predicateType' of the in-toto statement is missing.",
        )

    if not isinstance(predicate_type, str):
        raise ValidateInTotoPayloadError(
            "The value of attribute 'predicateType' in the in-toto statement is invalid: expecting a string."
        )

    predicate = payload.get("predicate")
    if predicate is not None and not isinstance(predicate, dict):
        raise ValidateInTotoPayloadError(
            "The value attribute 'predicate' in the in-toto statement is invalid: expecting an object.",
        )

    return True


def validate_intoto_subject(subject: JsonType) -> TypeGuard[InTotoSubject]:
    """Validate a single subject in the in-toto statement.

    See specification: https://github.com/in-toto/attestation/tree/main/spec/v0.1.0#statement.

    TODO: Consider using the in-toto-attestation package (https://github.com/in-toto/attestation/tree/main/python),
    which contains Python bindings for in-toto attestation.
    See issue: https://github.com/oracle/macaron/issues/426.

    Parameters
    ----------
    subject : JsonType
        The JSON element representing a single subject.

    Returns
    -------
    TypeGuard[InTotoSubject]
        ``True`` if the subject element is valid, in which case its type is narrowed to an
        ``InTotoSubject``; ``False`` otherwise.

    Raises
    ------
    ValidateInTotoPayloadError
        When the payload does not follow the expecting schema.
    """
    if not isinstance(subject, dict):
        raise ValidateInTotoPayloadError(
            "A subject in the in-toto statement is invalid: expecting an object.",
        )

    name = subject.get("name")
    if name is None:
        raise ValidateInTotoPayloadError("The attribute 'name' is missing from a subject.")
    if not isinstance(name, str):
        raise ValidateInTotoPayloadError(
            "The value of the attribute 'name' is invalid for a subject.",
        )

    digest_set = subject.get("digest")
    if digest_set is None:
        raise ValidateInTotoPayloadError(
            "The attribute 'digest' is missing from a subject.",
        )
    if not isinstance(digest_set, dict) or not is_valid_digest_set(digest_set):
        raise ValidateInTotoPayloadError(
            "The value of the attribute 'digest' is invalid for a subject.",
        )

    return True


def is_valid_digest_set(digest: dict[str, JsonType]) -> TypeGuard[dict[str, str]]:
    """Validate the digest set.

    Specification for the digest set: https://github.com/in-toto/attestation/blob/main/spec/v0.1.0/field_types.md#DigestSet.

    Parameters
    ----------
    digest : dict[str, JsonType]
        The digest set.

    Returns
    -------
    TypeGuard[dict[str, str]]
        ``True`` if the digest set is valid according to the spec, in which case its type
        is narrowed to a ``dict[str, str]``; ``False`` otherwise.
    """
    for value in digest.values():
        if not isinstance(value, str):
            return False
    return True
