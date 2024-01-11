# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""VSA schema and generation."""

from __future__ import annotations

import base64
import datetime
import json
import logging
from enum import StrEnum
from importlib import metadata as importlib_metadata
from typing import TypedDict

logger: logging.Logger = logging.getLogger(__name__)

# Note: The lint error "N815:mixedCase variable in class scope" is disabled for
# field names in the VSA to conform with in-toto naming conventions.


class Vsa(TypedDict):
    """The Macaron Verification Summary Attestation.

    For reference, see:

    * `SLSA <https://slsa.dev/spec/v1.0/verification_summary>`_.
    * `in-toto <https://github.com/in-toto/attestation/blob/main/spec/predicates/vsa.md>`_.
    """

    #: The payload type. Following in-toto, this is always ``application/vnd.in-toto+json``.
    payloadType: str  # noqa: N815

    #: The payload of the VSA, base64 encoded.
    payload: str


class VsaStatement(TypedDict):
    """The Statement layer of a Macaron VSA.

    For reference, see:

    * in-toto Statement layer specification: https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md.
    """

    #: Identifier for the schema of the Statement layer.
    #: This follows `in-toto v1 Statement layer schema
    #: <https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md>`_
    #: and is always ``https://in-toto.io/Statement/v1``.
    _type: str

    #: Subjects of the VSA.
    #: Each entry is a software component being verified by Macaron.
    #: Note: In the current version of Macaron, this field only contains one single
    #: software component, identified by a `PackageURL <https://github.com/package-url/purl-spec>`_.
    subject: list[dict]

    #: Identifier for the type of the Predicate.
    #: For Macaron-generated VSAs, this is always ``https://slsa.dev/verification_summary/v1``.
    predicateType: str  # noqa: N815

    #: The Predicate of the attestation, providing information about the verification.
    predicate: VsaPredicate


class VsaPredicate(TypedDict):
    """The 'predicate' field in the Statement layer of a Macaron VSA.

    For reference, see:

    * in-toto Predicate layer specification:
      https://github.com/in-toto/attestation/blob/main/spec/v1/predicate.md.
    * SLSA VSA predicate schema:
      https://slsa.dev/spec/v1.0/verification_summary#schema.
    """

    #: Identity of the verifier, as a tool carrying out the verification.
    verifier: Verifier

    #: The timestamp when the verification occurred.
    #: The field is a
    #: `Timestamp <https://github.com/in-toto/attestation/blob/main/spec/v1/field_types.md#Timestamp>`_.
    timeVerified: str  # noqa: N815

    #: URI that identifies the resource associated with the software component being verified.
    #: This field is a
    #: `ResourceURI <https://github.com/in-toto/attestation/blob/main/spec/v1/field_types.md#ResourceURI>`_.
    #: Currently, this has the same value as the subject of the VSA, i.e. the PURL of
    #: the software component being verified against.
    resourceUri: str  # noqa: N815

    #: The policy that the subject software component was verified against.
    #: This field is a
    #: `ResourceDescriptor <https://github.com/in-toto/attestation/blob/main/spec/v1/resource_descriptor.md>`_.
    policy: Policy

    #: The verification result.
    verificationResult: VerificationResult  # noqa: N815

    #: According to SLSA, this field "indicates the highest level of each track verified
    #: for the artifact (and not its dependencies), or ``FAILED`` if policy verification failed".
    #: We currently leave this list empty.
    verifiedLevels: list  # noqa: N815


class Verifier(TypedDict):
    """The 'verifier' field within the Macaron VSA predicate field.

    This field provides the identity of the verifier, as well as the versioning details of its components.
    """

    #: The identity of the verifier as a
    #:   `TypeURI <https://github.com/in-toto/attestation/blob/main/spec/v1/field_types.md#TypeURI>`_.
    id: str  # noqa: A003

    #: A mapping from components of the verifier and their corresponding versions.
    #: At the moment, this field only includes Macaron itself.
    version: dict[str, str]


class Policy(TypedDict):
    """The 'policy' field within the Macaron VSA predicate field.

    This field provides information about the policy used for verification.
    """

    #: The Souffle Datalog code defining the policy in plain text.
    content: str


class VerificationResult(StrEnum):
    """Verification result, which is either 'PASSED' or 'FAILED'."""

    FAILED = "FAILED"
    PASSED = "PASSED"


def create_vsa_statement(
    subject_purl: str,
    policy_content: str,
    verification_result: VerificationResult,
) -> VsaStatement:
    """Construct the Statement layer of the VSA.

    Parameters
    ----------
    subject_purl : str
        The PURL (string) of the subject of the VSA. This identifies the unique
        software component that the policy applies to.
    policy_content : str
        The Souffle policy code defining the policy.
    verification_result : VerificationResult
        The verification result of the subject.

    Returns
    -------
    VsaStatement
        A Statement layer of the VSA.
    """
    return VsaStatement(
        _type="https://in-toto.io/Statement/v1",
        subject=[
            {
                "uri": subject_purl,
            }
        ],
        predicateType="https://slsa.dev/verification_summary/v1",
        predicate=VsaPredicate(
            verifier=Verifier(
                id="https://github.com/oracle/macaron",
                version={
                    "macaron": importlib_metadata.version("macaron"),
                },
            ),
            timeVerified=datetime.datetime.now(tz=datetime.UTC).isoformat(),
            resourceUri=subject_purl,
            policy={
                "content": policy_content,
            },
            verificationResult=verification_result,
            verifiedLevels=[],
        ),
    )


def get_subject_verification_result(policy_result: dict) -> tuple[str, VerificationResult] | None:
    """Get the PURL (string) and verification result of the single software component the policy applies to.

    This is currently done by reading the facts of two relations:
    ``component_violates_policy``, and ``component_satisfies_policy``
    from the result of the policy engine.

    We define two PURLs to be different if the two PURL strings are different.

    The result of this function depends on the policy engine result:

    - If there exist multiple different PURLs, this function returns ``None``.
    - If there exist multiple occurrences of the same PURL and it is the only unique
      PURL in the policy engine result, this function returns the latest occurrence,
      which is the PURL that goes with the highest component ID, taking advantage of
      component IDs being auto-incremented.
    - If there is no PURL in the result, i.e. the policy applies to no software component
      in the database, this function also returns ``None``.

    Parameters
    ----------
    policy_result : dict
        The result of the policy engine, including two relations:
        ``component_violates_policy``, and ``component_satisfies_policy``.

    Returns
    -------
    tuple[str, VerificationResult] | None
        A pair of PURL and verification result of the only software component that
        the policy applies to, or ``None`` according to the aforementioned conditions.
    """
    component_violates_policy_facts = policy_result.get("component_violates_policy", [])
    component_satisfies_policy_facts = policy_result.get("component_satisfies_policy", [])

    # key: PURL; value: result with the highest component id
    component_results: dict[str, tuple[int, VerificationResult]] = {}

    for component_id_string, purl, _ in component_violates_policy_facts:
        try:
            component_id = int(component_id_string)
        except ValueError:
            logger.error("Expected component id %s to be an integer.", component_id_string)
            return None
        if purl not in component_results:
            component_results[purl] = (component_id, VerificationResult.FAILED)
        else:
            current_component_id, _ = component_results[purl]
            if component_id > current_component_id:
                component_results[purl] = (component_id, VerificationResult.FAILED)
    for component_id_string, purl, _ in component_satisfies_policy_facts:
        try:
            component_id = int(component_id_string)
        except ValueError:
            logger.error("Expected component id %s to be an integer.", component_id_string)
            return None
        if purl not in component_results:
            component_results[purl] = (component_id, VerificationResult.PASSED)
        else:
            current_component_id, _ = component_results[purl]
            if component_id > current_component_id:
                component_results[purl] = (component_id, VerificationResult.PASSED)

    if len(component_results) != 1:
        if len(component_results) == 0:
            logger.info("The policy applies to no software components.")
        if len(component_results) > 1:
            logger.info("The policy applies to more than one software components.")
        logger.info("No VSA will be generated.")
        return None

    subject_purl = next(iter(component_results.keys()))
    _, verification_result = component_results[subject_purl]

    return subject_purl, verification_result


def generate_vsa(policy_content: str, policy_result: dict) -> Vsa | None:
    """Generate a VSA, if appropriate, based on the result of the policy engine.

    Parameters
    ----------
    policy_content : str
        The Souffle policy code defining the policy.
    policy_result : dict
        The result of the policy engine.

    Returns
    -------
    Vsa | None
        The VSA, or ``None`` if generating a VSA is not appropriate according
        to the policy engine result.
    """
    subject_verification_result = get_subject_verification_result(policy_result)

    if subject_verification_result is None:
        return None

    subject_purl, verification_result = subject_verification_result

    unencoded_payload = create_vsa_statement(
        subject_purl=subject_purl,
        policy_content=policy_content,
        verification_result=verification_result,
    )

    try:
        payload = json.dumps(unencoded_payload)
    except (TypeError, RecursionError, ValueError) as err:
        logger.debug("Error encountered while deserializing the VSA payload: %s", err)
        return None

    try:
        payload_bytes = payload.encode()
    except UnicodeError as err:
        logger.debug("Error encountered while byte-encoding the VSA payload: %s", err)
        return None

    try:
        encoded_payload_bytes = base64.b64encode(payload_bytes)
    except (ValueError, TypeError) as err:
        logger.debug("Error encountered while base64-encoding the VSA payload: %s", err)
        return None

    try:
        encoded_payload = encoded_payload_bytes.decode("ascii")
    except (ValueError, TypeError) as err:
        logger.debug("Error encountered while converting the base64-encoded VSA payload to string: %s", err)
        return None

    return Vsa(
        payloadType="application/vnd.in-toto+json",
        payload=encoded_payload,
    )
