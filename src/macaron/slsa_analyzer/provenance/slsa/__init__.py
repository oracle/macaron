# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements SLSA provenance abstractions."""

from typing import NamedTuple

from macaron.slsa_analyzer.asset import AssetLocator
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload
from macaron.slsa_analyzer.provenance.intoto.v01 import InTotoV01Subject
from macaron.slsa_analyzer.provenance.intoto.v1 import InTotoV1ResourceDescriptor


class SLSAProvenanceData(NamedTuple):
    """SLSA provenance data."""

    #: The provenance asset.
    asset: AssetLocator
    #: The provenance payload.
    payload: InTotoPayload


def extract_build_artifacts_from_slsa_subjects(
    payload: InTotoPayload,
) -> list[InTotoV01Subject | InTotoV1ResourceDescriptor]:
    """Extract subjects that are build artifacts from the ``"subject"`` field of the provenance.

    Each artifact subject is assumed to have a sha256 digest. If a sha256 digest is not present for
    a subject, that subject is ignored.

    Parameters
    ----------
    payload : InTotoPayload
        The provenance payload.

    Returns
    -------
    list[InTotoV01Subject | InTotoV1ResourceDescriptor]
        A list of subjects in the ``"subject"`` field of the provenance that are build artifacts.
    """
    subjects = payload.statement["subject"]
    artifact_subjects = []
    for subject in subjects:
        digest = subject["digest"]
        if not digest:
            continue
        sha256 = digest.get("sha256")
        if not sha256 or not isinstance(sha256, str):
            continue
        artifact_subjects.append(subject)

    return artifact_subjects


def is_slsa_provenance_payload(
    payload: InTotoPayload,
    predicate_types: list[str],
) -> bool:
    """Check if the given provenance payload is a SLSA provenance payload.

    Parameters
    ----------
    payload : InTotoPayload
        The provenance payload.
    predicate_types : list[str]
        The allowed values for the ``"predicateType"`` field of the provenance payload.

    Returns
    -------
    bool
        ``True`` if the payload is a witness provenance payload, ``False`` otherwise.
    """
    return payload.statement["predicateType"] in predicate_types
