# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module handles in-toto version 1 attestations."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import TypedDict, TypeGuard

from macaron.slsa_analyzer.provenance.intoto.errors import ValidateInTotoPayloadError
from macaron.util import JsonType

# The full list of cryptographic algorithms supported in SLSA v1 provenance. These are used as keys within the digest
#  set of the resource descriptors within the subject.
# See: https://github.com/in-toto/attestation/blob/main/spec/v1/digest_set.md
VALID_ALGORITHMS = [
    "sha256",
    "sha224",
    "sha384",
    "sha512",
    "sha512_224",
    "sha512_256",
    "sha3_224",
    "sha3_256",
    "sha3_384",
    "sha3_512",
    "shake128",
    "shake256",
    "blake2b",
    "blake2s",
    "ripemd160",
    "sm3",
    "gost",
    "sha1",
    "md5",
]


class InTotoV1Statement(TypedDict):
    """An in-toto version 1 statement.

    This is the type of the payload in a version 1 in-toto attestation.
    Specification: https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md.
    """

    _type: str
    subject: list[InTotoV1ResourceDescriptor]
    predicateType: str  # noqa: N815
    predicate: dict[str, JsonType] | None


class InTotoV1ResourceDescriptor(TypedDict):
    """An in-toto resource descriptor.

    Specification: https://github.com/in-toto/attestation/blob/main/spec/v1/resource_descriptor.md
    """

    name: str | None
    uri: str | None
    digest: dict[str, str] | None
    content: str | None
    download_location: str | None
    media_type: str | None
    annotations: dict[str, JsonType] | None


def validate_intoto_statement(payload: dict[str, JsonType]) -> TypeGuard[InTotoV1Statement]:
    """Validate the statement of an in-toto attestation.

    Specification: https://github.com/in-toto/attestation/tree/main/spec/v1/statement.md.

    Parameters
    ----------
    payload : dict[str, JsonType]
        The JSON statement after being base64-decoded.

    Returns
    -------
    TypeGuard[InTotoStatement]
        ``True`` if the attestation statement is valid, in which case its type is narrowed to an
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
    if not isinstance(type_, str) or not type_ == "https://in-toto.io/Statement/v1":
        raise ValidateInTotoPayloadError(
            "The value of attribute '_type' in the in-toto statement must be: 'https://in-toto.io/Statement/v1'",
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


def validate_intoto_subject(subject: JsonType) -> TypeGuard[InTotoV1ResourceDescriptor]:
    """Validate a single subject in the in-toto statement.

    See specification: https://github.com/in-toto/attestation/blob/main/spec/v1/resource_descriptor.md

    Parameters
    ----------
    subject : JsonType
        The JSON element representing a single subject.

    Returns
    -------
    TypeGuard[InTotoV1ResourceDescriptor]
        ``True`` if the subject element is valid, in which case its type is narrowed to an
        ``InTotoV1ResourceDescriptor``; ``False`` otherwise.

    Raises
    ------
    ValidateInTotoPayloadError
        When the payload does not follow the expecting schema.
    """
    if not isinstance(subject, dict):
        raise ValidateInTotoPayloadError(
            "A subject in the in-toto statement is invalid: expecting an object.",
        )

    # At least one of 'uri', 'digest', and 'content' must be valid and present.
    uri_state = _validate_property(subject, "uri", True, lambda x: isinstance(x, str), False)
    content_state = _validate_property(subject, "content", True, lambda x: isinstance(x, str), False)
    digest_state = _validate_property(subject, "digest", True, is_valid_digest_set, False)
    if _ValidityState.VALID not in (uri_state, content_state, digest_state):
        raise ValidateInTotoPayloadError(
            f"One of 'uri', 'digest', or 'content' must be present and valid within 'subject'. URI: {uri_state.name}. "
            f"Content: {content_state.name}. DIGEST: {digest_state.name}."
        )

    _validate_property(subject, "name", False, lambda x: isinstance(x, str))
    _validate_property(subject, "downloadLocation", False, lambda x: isinstance(x, str))
    _validate_property(subject, "mediaType", False, lambda x: isinstance(x, str))
    _validate_property(subject, "annotations", False, is_valid_annotation_map)

    return True


def is_valid_digest_set(digest: JsonType) -> bool:
    """Validate the digest set.

    Specification for the digest set: https://github.com/in-toto/attestation/blob/main/spec/v1/digest_set.md.

    Parameters
    ----------
    digest : JsonType
        The digest set.

    Returns
    -------
    bool:
        ``True`` if the digest is valid according to the spec.
    """
    if not isinstance(digest, dict):
        return False
    for key in digest:
        if key not in VALID_ALGORITHMS:
            return False
        if not isinstance(digest[key], str):
            return False
    return True


def is_valid_annotation_map(annotation_map: JsonType) -> bool:
    """Validate the annotation map which is a dictionary with string keys and JsonType values.

    Parameters
    ----------
    annotation_map : JsonType
        The annotation map dictionary.

    Returns
    -------
    bool:
        ``True`` if the annotation map is valid according to the spec.
    """
    if not isinstance(annotation_map, dict):
        return False
    return True


def _validate_property(
    object_: JsonType,
    key: str,
    required: bool,
    validator_function: Callable[[JsonType], bool],
    report_errors: bool = True,
) -> _ValidityState:
    """Validate the existence and type of target within the passed Json object."""
    if not isinstance(object_, dict):
        # The passed object is checked before this function is called, but mypy requires it be explicitly checked here
        #  too. Also known as: this branch should never be taken.
        return _ValidityState.INVALID

    value = object_.get(key)
    if not value:
        if required:
            if report_errors:
                raise ValidateInTotoPayloadError(f"The attribute {key} of the in-toto subject is missing.")
            return _ValidityState.MISSING
        return _ValidityState.VALID

    valid = validator_function(value)
    if not valid:
        if report_errors:
            raise ValidateInTotoPayloadError(f"The attribute {key} of the in-toto subject is invalid.")
        return _ValidityState.INVALID
    return _ValidityState.VALID


class _ValidityState(str, Enum):
    """Represents the validity state of properties being validated."""

    VALID = 0
    MISSING = 1
    INVALID = 2
