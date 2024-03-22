# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains methods for extracting repository and commit metadata from provenance files."""
import logging

from macaron.errors import JsonError, ProvenanceError
from macaron.json_tools import json_extract
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, InTotoV1Payload, InTotoV01Payload
from macaron.util import JsonType

logger: logging.Logger = logging.getLogger(__name__)


SLSA_V01_DIGEST_SET_GIT_ALGORITHMS = ["sha1"]
SLSA_V02_DIGEST_SET_GIT_ALGORITHMS = ["sha1"]
SLSA_V1_DIGEST_SET_GIT_ALGORITHMS = ["sha1", "gitCommit"]


def extract_repo_and_commit_from_provenance(payload: InTotoPayload) -> tuple[str, str]:
    """Extract the repository and commit metadata from the passed provenance payload.

    Parameters
    ----------
    payload: InTotoPayload
        The payload to extract from.

    Returns
    -------
    tuple[str, str]
        The repository URL and commit hash if found, a pair of empty strings otherwise.

    Raises
    ------
    ProvenanceError
        If the extraction process fails for any reason.
    """
    repo = ""
    commit = ""
    predicate_type = payload.statement.get("predicateType")
    try:
        if isinstance(payload, InTotoV1Payload):
            if predicate_type == "https://slsa.dev/provenance/v1":
                repo, commit = _extract_from_slsa_v1(payload)
        elif isinstance(payload, InTotoV01Payload):
            if predicate_type == "https://slsa.dev/provenance/v0.2":
                repo, commit = _extract_from_slsa_v02(payload)
            if predicate_type == "https://slsa.dev/provenance/v0.1":
                repo, commit = _extract_from_slsa_v01(payload)
            if predicate_type == "https://witness.testifysec.com/attestation-collection/v0.1":
                repo, commit = _extract_from_witness_provenance(payload)
    except JsonError as error:
        logger.debug(error)
        raise ProvenanceError("JSON exception while extracting from provenance.") from error

    if not repo or not commit:
        msg = (
            f"Extraction from provenance not supported for versions: "
            f"predicate_type {predicate_type}, in-toto {str(type(payload))}."
        )
        logger.debug(msg)
        raise ProvenanceError(msg)

    logger.debug("Extracted repo and commit from provenance: %s, %s", repo, commit)
    return repo, commit


def _extract_from_slsa_v01(payload: InTotoV01Payload) -> tuple[str, str]:
    """Extract the repository and commit metadata from the slsa v01 provenance payload."""
    predicate: dict[str, JsonType] | None = payload.statement.get("predicate")
    if not predicate:
        raise ProvenanceError("No predicate in payload statement.")

    # The repository URL and commit are stored inside an entry in the list of predicate -> materials.
    # In predicate -> recipe -> definedInMaterial we find the list index that points to the correct entry.
    list_index = json_extract(predicate, ["recipe", "definedInMaterial"], int)
    material_list = json_extract(predicate, ["materials"], list)
    if list_index >= len(material_list):
        raise ProvenanceError("Material list index outside of material list bounds.")
    material = material_list[list_index]
    if not material or not isinstance(material, dict):
        raise ProvenanceError("Indexed material list entry is invalid.")

    uri = json_extract(material, ["uri"], str)

    repo = _clean_spdx(uri)

    digest_set = json_extract(material, ["digest"], dict)
    commit = _extract_commit_from_digest_set(digest_set, SLSA_V01_DIGEST_SET_GIT_ALGORITHMS)

    if not commit:
        raise ProvenanceError("Failed to extract commit hash from provenance.")

    return repo, commit


def _extract_from_slsa_v02(payload: InTotoV01Payload) -> tuple[str, str]:
    """Extract the repository and commit metadata from the slsa v02 provenance payload."""
    predicate: dict[str, JsonType] | None = payload.statement.get("predicate")
    if not predicate:
        raise ProvenanceError("No predicate in payload statement.")

    # The repository URL and commit are stored within the predicate -> invocation -> configSource object.
    # See https://slsa.dev/spec/v0.2/provenance
    uri = json_extract(predicate, ["invocation", "configSource", "uri"], str)
    if not uri:
        raise ProvenanceError("Failed to extract repository URL from provenance.")
    repo = _clean_spdx(uri)

    digest_set = json_extract(predicate, ["invocation", "configSource", "digest"], dict)
    commit = _extract_commit_from_digest_set(digest_set, SLSA_V02_DIGEST_SET_GIT_ALGORITHMS)

    if not commit:
        raise ProvenanceError("Failed to extract commit hash from provenance.")

    return repo, commit


def _extract_from_slsa_v1(payload: InTotoV1Payload) -> tuple[str, str]:
    """Extract the repository and commit metadata from the slsa v1 provenance payload."""
    predicate: dict[str, JsonType] | None = payload.statement.get("predicate")
    if not predicate:
        raise ProvenanceError("No predicate in payload statement.")

    build_def = json_extract(predicate, ["buildDefinition"], dict)
    build_type = json_extract(build_def, ["buildType"], str)

    # Extract the repository URL.
    repo = ""
    if build_type == "https://slsa-framework.github.io/gcb-buildtypes/triggered-build/v1":
        try:
            repo = json_extract(build_def, ["externalParameters", "sourceToBuild", "repository"], str)
        except JsonError:
            repo = json_extract(build_def, ["externalParameters", "configSource", "repository"], str)
    if build_type == "https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1":
        repo = json_extract(build_def, ["externalParameters", "workflow", "repository"], str)

    if not repo:
        raise ProvenanceError("Failed to extract repository URL from provenance.")

    # Extract the commit hash.
    commit = ""
    deps = json_extract(build_def, ["resolvedDependencies"], list)
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        uri = json_extract(dep, ["uri"], str)
        url = _clean_spdx(uri)
        if url != repo:
            continue
        digest_set = json_extract(dep, ["digest"], dict)
        commit = _extract_commit_from_digest_set(digest_set, SLSA_V1_DIGEST_SET_GIT_ALGORITHMS)

    if not commit:
        raise ProvenanceError("Failed to extract commit hash from provenance.")

    return repo, commit


def _extract_from_witness_provenance(payload: InTotoV01Payload) -> tuple[str, str]:
    """Extract the repository and commit metadata from the witness provenance file found at the passed path.

    To successfully return the commit and repository URL, the payload must respectively contain a Git attestation, and
    either a GitHub or GitLab attestation.

    Parameters
    ----------
    payload: InTotoPayload
        The payload to extract from.

    Returns
    -------
    tuple[str, str]
        The repository URL and commit hash if found, a pair of empty strings otherwise.
    """
    predicate: dict[str, JsonType] | None = payload.statement.get("predicate")
    if not predicate:
        raise ProvenanceError("No predicate in payload statement.")

    attestations = json_extract(predicate, ["attestations"], list)
    commit = ""
    repo = ""
    for entry in attestations:
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type")
        if not entry_type:
            continue
        if entry_type.startswith("https://witness.dev/attestations/git/"):
            commit = json_extract(entry, ["attestation", "commithash"], str)
        elif entry_type.startswith("https://witness.dev/attestations/gitlab/") or entry_type.startswith(
            "https://witness.dev/attestations/github/"
        ):
            repo = json_extract(entry, ["attestation", "projecturl"], str)

    if not commit or not repo:
        raise ProvenanceError("Could not extract repo and commit from provenance.")

    return repo, commit


def _extract_commit_from_digest_set(digest_set: dict[str, JsonType], valid_algorithms: list[str]) -> str:
    """Extract the commit from the passed DigestSet.

    The DigestSet is an in-toto object that maps algorithm types to commit hashes (digests).
    """
    if len(digest_set.keys()) > 1:
        logger.debug("DigestSet contains multiple algorithms: %s", digest_set.keys())

    for key in digest_set:
        if key in valid_algorithms:
            value = digest_set.get(key)
            if isinstance(value, str):
                return value
    raise ProvenanceError(f"No valid digest in digest set: {digest_set.keys()} not in {valid_algorithms}")


def _clean_spdx(uri: str) -> str:
    """Clean the passed SPDX URI and return the normalised URL it represents.

    A SPDX URI has the form: git+https://example.com@refs/heads/main
    """
    url, _, _ = uri.lstrip("git+").rpartition("@")
    return url
