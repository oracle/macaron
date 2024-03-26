# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Witness provenance (https://github.com/testifysec/witness)."""

import logging
from typing import NamedTuple

from macaron.config.defaults import defaults
from macaron.slsa_analyzer.asset import AssetLocator
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, InTotoV01Payload
from macaron.slsa_analyzer.provenance.intoto.v01 import InTotoV01Subject
from macaron.slsa_analyzer.provenance.witness.attestor import GitLabWitnessAttestor, RepoAttestor

logger: logging.Logger = logging.getLogger(__name__)


class WitnessProvenanceData(NamedTuple):
    """Data of a downloaded witness provenance."""

    #: The provenance asset.
    asset: AssetLocator
    #: The provenance payload.
    payload: InTotoPayload


class WitnessVerifierConfig(NamedTuple):
    """Configuration for verifying witness provenances."""

    #: A provenance payload is recognized by Macaron to be a witness provenance if
    #: its ``predicateType`` value is present within this set.
    predicate_types: set[str]
    #: A set of artifact extensions to verify. Artifacts having an extension outside this list are not verified.
    artifact_extensions: set[str]


def load_witness_verifier_config() -> WitnessVerifierConfig:
    """Load configuration for verifying witness provenances.

    Returns
    -------
    WitnessVerifierConfig
        Configuration for verifying witness provenances.
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
    payload: InTotoPayload,
    predicate_types: set[str],
) -> bool:
    """Check if the given provenance payload is a witness provenance payload.

    Parameters
    ----------
    payload : InTotoPayload
        The provenance payload.
    predicate_types : set[str]
        The allowed values for the ``"predicateType"`` field of the provenance payload.

    Returns
    -------
    bool
        ``True`` if the payload is a witness provenance payload, ``False`` otherwise.
    """
    # TODO: add support for in-toto v1 provenances.
    return isinstance(payload, InTotoV01Payload) and payload.statement["predicateType"] in predicate_types


class WitnessProvenanceSubject(NamedTuple):
    """A helper class to store elements of the ``subject`` list in the provenances."""

    #: The ``"name"`` field of each ``subject``.
    subject_name: str
    #: The SHA256 digest of the corresponding asset to the subject.
    sha256_digest: str

    @property
    def artifact_name(self) -> str:
        """Get the artifact name, which should be the last part of the subject."""
        _, _, artifact_name = self.subject_name.rpartition("/")
        return artifact_name


def extract_repo_url(witness_payload: InTotoPayload) -> str | None:
    """Extract the repo URL from the witness provenance payload.

    Parameters
    ----------
    witness_payload : InTotoPayload
        The witness provenance payload.

    Returns
    -------
    str | None
        The repo URL within the witness provenance payload, if the provenance payload
        can be processed and the repo URL is found.
    """
    repo_attestors: list[RepoAttestor] = [GitLabWitnessAttestor()]

    for attestor in repo_attestors:
        repo_url = attestor.extract_repo_url(witness_payload)
        if repo_url is not None:
            return repo_url

    return None


def extract_build_artifacts_from_witness_subjects(witness_payload: InTotoPayload) -> list[InTotoV01Subject]:
    """Read the ``"subjects"`` field of the provenance to obtain the hash digests of each subject.

    Parameters
    ----------
    witness_payload : InTotoPayload
        The witness provenance payload.
    extensions : list[str]
        The allowed extensions of the subjects.
        All subjects with names not ending in these extensions are ignored.

    Returns
    -------
    list[InTotoV01Subject]
        A dictionary in which each key is a subject name and each value is the corresponding SHA256 digest.
    """
    if not isinstance(witness_payload, InTotoV01Payload):
        return []

    subjects = witness_payload.statement["subject"]
    artifact_subjects = []
    for subject in subjects:
        # Filter all subjects attested by the product attestor, which records all changed and
        # created files in the build process.
        # Documentation: https://github.com/in-toto/witness/blob/main/docs/attestors/product.md
        if not subject["name"].startswith("https://witness.dev/attestations/product/v0.1/file:"):
            continue

        digest = subject["digest"]
        sha256 = digest.get("sha256")
        if not sha256 or not isinstance(sha256, str):
            continue
        artifact_subjects.append(subject)

    return artifact_subjects
