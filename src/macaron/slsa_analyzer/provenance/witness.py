# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Witness provenance (https://github.com/testifysec/witness)."""

import logging
from typing import NamedTuple, TypeGuard

from macaron.config.defaults import defaults
from macaron.slsa_analyzer.asset import IsAsset
from macaron.util import JsonType

logger: logging.Logger = logging.getLogger(__name__)


class WitnessProvenance(NamedTuple):
    """Witness provenance."""

    asset: IsAsset
    payload: dict[str, JsonType]


class WitnessVerifierConfig(NamedTuple):
    """Configuration for verifying witness provenances.

    Attributes
    ----------
    predicate_types: set[str]
        A provenance payload is recognized by Macaron to be a witness provenance if its
        ``predicateType`` value is present within this set.
    artifact_extensions : set[str]
        A set of artifact extensions to verify. Artifacts having an extension outside this list
        are not verified.
    """

    predicate_types: set[str]
    artifact_extensions: set[str]


def load_witness_verifier_config() -> WitnessVerifierConfig:
    """Load configuration for verifying witness provenances.

    Returns
    -------
    WitnessVerifierConfig
        Configuration for verifying witness provenance.
    """
    return WitnessVerifierConfig(
        predicate_types=set(
            defaults.get_list(
                "provenance.witness",
                "predicate_types",
                fallback=[],
            )
        ),
        artifact_extensions=set(
            defaults.get_list(
                "provenance.witness",
                "artifact_extensions",
                fallback=[],
            )
        ),
    )


def is_witness_provenance_payload(
    payload: dict[str, JsonType],
    predicate_types: set[str],
) -> TypeGuard[dict[str, JsonType]]:
    """Check if the given provenance payload is a witness provenance payload.

    Parameters
    ----------
    payload : JsonType
        The provenance payload.
    predicate_types : set[str]
        The allowed values for the ``"predicateType"`` field of the provenance payload.

    Returns
    -------
    TypeGuard[dict[str, JsonType]]
        ``True`` if the payload is a witness provenance payload, ``False`` otherwise.
        If ``True`` is returned, the type of ``payload`` is narrowed to be a JSON object,
        or ``dict[str, JsonType]`` in Python type.
    """
    predicate_type = payload.get("predicateType")
    if predicate_type is None:
        logger.debug("Malformed provenance payload: missing the 'predicateType' field.")
        return False
    return predicate_type in predicate_types


class WitnessProvenanceSubject(NamedTuple):
    """A helper class to store elements of the ``subject`` list in the provenances.

    Attributes
    ----------
    subject_name : str
        The ``"name"`` field of each ``subject``.
    sha256 : str
        The SHA256 digest of the corresponding asset to the subject.
    """

    subject_name: str
    sha256_digest: str

    @property
    def artifact_name(self) -> str:
        """Get the artifact name, which should be the last part of the subject."""
        _, _, artifact_name = self.subject_name.rpartition("/")
        return artifact_name


def extract_repo_url(witness_payload: dict[str, JsonType]) -> str | None:
    """Extract the repo URL from the witness provenance payload.

    Parameters
    ----------
    witness_payload : dict[str, JsonType]
        The witness provenance payload.

    Returns
    -------
    str | None
        The repo URL within the witness provenance payload, if the provenance payload
        can be processed and the repo URL is found.
    """
    predicates = witness_payload.get("predicates", {})
    if predicates is None or not isinstance(predicates, dict):
        return None
    attestations = predicates.get("attestations", [])
    if attestations is None or not isinstance(attestations, list):
        return None
    for attestation_entry in attestations:
        if not isinstance(attestation_entry, dict):
            return None
        attestation_type = attestation_entry.get("type")
        if attestation_type != "https://witness.dev/attestations/gitlab/v0.1":
            continue
        attestation = attestation_entry.get("attestation")
        if attestation is None or not isinstance(attestation, dict):
            return None
        project_url = attestation.get("projecturl")
        if project_url is None or not isinstance(project_url, str):
            return None
        return project_url
    return None


def extract_witness_provenance_subjects(witness_payload: dict[str, JsonType]) -> list[WitnessProvenanceSubject]:
    """Read the ``"subjects"`` field of the provenance to obtain the hash digests of each subject.

    Parameters
    ----------
    witness_payload : dict[str, JsonType]
        The witness provenance payload.
    extensions : list[str]
        The allowed extensions of the subjects.
        All subjects with names not ending in these extensions are ignored.

    Returns
    -------
    dict[str, str]
        A dictionary in which each key is a subject name and each value is the corresponding SHA256 digest.
    """
    subjects = witness_payload.get("subject")
    if subjects is None:
        logger.debug("Could not find the 'subject' field in the witness provenance payload.")
        return []

    if not isinstance(subjects, list):
        logger.debug(
            "Got unexpected value type for the 'subject' field in the witness provenance payload. Expected a list."
        )
        return []

    subject_digests = []

    for subject in subjects:
        if not isinstance(subject, dict):
            logger.debug("Got unexpected value type for an element in the 'subject' list. Expected a JSON object.")
            continue

        name = subject.get("name")
        if not name or not isinstance(name, str):
            continue

        digest = subject.get("digest")
        if not digest or not isinstance(digest, dict):
            continue
        sha256 = digest.get("sha256")
        if not sha256 or not isinstance(sha256, str):
            continue

        subject_digests.append(
            WitnessProvenanceSubject(
                subject_name=name,
                sha256_digest=sha256,
            )
        )

    return subject_digests
