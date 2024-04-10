# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""VSA schema and generation."""

from __future__ import annotations

import base64
import datetime
import json
import logging
from collections.abc import Iterable
from enum import StrEnum
from importlib import metadata as importlib_metadata
from typing import TypedDict

import sqlalchemy
from packageurl import PackageURL
from sqlalchemy.orm import Session

from macaron.database.database_manager import get_db_manager
from macaron.database.table_definitions import ProvenanceSubject
from macaron.util import JsonType

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


def get_common_purl_from_artifact_purls(purl_strs: Iterable[str]) -> str | None:
    """Get a single common PackageURL given some artifact PackageURLs.

    Assumption: A package may have more than one artifact. If each artifact is identified
    by a PackageURL, these PackageURLs still share the type, namespace, name, and
    version values. The common PackageURL contains these values.
    """
    try:
        purls = [PackageURL.from_string(purl_str) for purl_str in purl_strs]
    except ValueError:
        return None

    if len(purls) == 0:
        return None

    purl_type = purls[0].type
    namespace = purls[0].namespace
    name = purls[0].name
    version = purls[0].version

    for purl in purls:
        if any(
            [
                purl_type != purl.type,
                namespace != purl.namespace,
                name != purl.name,
                version != purl.version,
            ]
        ):
            return None

    common_purl = PackageURL(type=purl_type, namespace=namespace, name=name, version=version)
    return str(common_purl)


def create_vsa_statement(
    passed_components: dict[str, int],
    policy_content: str,
) -> VsaStatement | None:
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
    subjects = []

    try:
        with Session(get_db_manager().engine) as session, session.begin():
            for purl, component_id in passed_components.items():
                try:
                    provenance_subject = (
                        session.execute(
                            sqlalchemy.select(ProvenanceSubject).where(ProvenanceSubject.component_id == component_id)
                        )
                        .scalars()
                        .one()
                    )
                    sha256 = provenance_subject.sha256
                except sqlalchemy.orm.exc.NoResultFound:
                    sha256 = None
                    logger.debug("No digest stored for software component '%s'.", purl)
                except sqlalchemy.orm.exc.MultipleResultsFound as e:
                    logger.debug(
                        "Unexpected database query result. "
                        "Expected no more than one result when retrieving SHA256 of a provenance subject. "
                        "Error: %s",
                        e,
                    )
                    continue

                subject: dict[str, JsonType] = {
                    "uri": purl,
                }
                if sha256:
                    subject["digest"] = {
                        "sha256": sha256,
                    }

                subjects.append(subject)

    except sqlalchemy.exc.SQLAlchemyError as error:
        logger.debug("Cannot retrieve hash digest of software components: %s.", error)
        return None

    return VsaStatement(
        _type="https://in-toto.io/Statement/v1",
        subject=subjects,
        predicateType="https://slsa.dev/verification_summary/v1",
        predicate=VsaPredicate(
            verifier=Verifier(
                id="https://github.com/oracle/macaron",
                version={
                    "macaron": importlib_metadata.version("macaron"),
                },
            ),
            timeVerified=datetime.datetime.now(tz=datetime.UTC).isoformat(),
            resourceUri=get_common_purl_from_artifact_purls(passed_components.keys()) or "",
            policy={
                "content": policy_content,
            },
            verificationResult=VerificationResult.PASSED,
            verifiedLevels=[],
        ),
    )


def get_components_passing_policy(policy_result: dict) -> dict[str, int] | None:
    """Get the verification result in the form of PURLs and component ids of software artifacts passing the policy.

    This is currently done by reading the facts of two relations:
    ``component_violates_policy``, and ``component_satisfies_policy``
    from the result of the policy engine.

    The result of this function depends on the policy engine result.

    If there exist any software component failing the policy, this function returns ``None``.

    When all software components in the result pass the policy, if there exist multiple occurrences
    of the same PURL, this function returns the latest occurrence, which is the one with the highest
    component id, taking advantage of component ids being auto-incremented.

    If there is no PURL in the result, i.e. the policy applies to no software component in the database,
    this function also returns ``None``.

    Parameters
    ----------
    policy_result : dict
        The result of the policy engine, including two relations:
        ``component_violates_policy``, and ``component_satisfies_policy``.

    Returns
    -------
    dict[str, int] | None
        A dictionary of software components passing the policy, or ``None`` if there is any
        component failing the policy or if there is no software component in the policy engine result.
        Each key is a PackageURL of the software component, and each value is the corresponding
        component id of that component.
    """
    component_violates_policy_facts = policy_result.get("component_violates_policy", [])
    component_satisfies_policy_facts = policy_result.get("component_satisfies_policy", [])

    if len(component_violates_policy_facts) > 0:
        logger.info("Encountered software component failing the policy. No VSA is generated.")
        return None

    # This dictionary deduplicates multiple occurrences of the same PURL in the
    # ``component_satisfies_policy_facts`` result, which may occur because the same PURL
    # may appear multiple times in the ``_component`` table of the database.
    # Here, we are only taking the latest result into consideration.
    # Each key is a PURL and each value is the the highest component id of the
    # corresponding PURL, taking advantage of the component id column being auto-incremented.
    passed_components: dict[str, int] = {}

    for component_id_string, purl, _ in component_satisfies_policy_facts:
        try:
            component_id = int(component_id_string)
        except ValueError:
            logger.error("Expected component id %s to be an integer.", component_id_string)
            return None
        if purl not in passed_components:
            passed_components[purl] = component_id
        else:
            current_component_id = passed_components[purl]
            if component_id > current_component_id:
                passed_components[purl] = component_id

    if len(passed_components) == 0:
        return None

    return passed_components


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
    passed_components = get_components_passing_policy(policy_result)

    if passed_components is None:
        return None

    unencoded_payload = create_vsa_statement(
        passed_components,
        policy_content=policy_content,
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
