# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains methods for extracting repository and commit metadata from provenance files."""
import logging
from typing import overload

from macaron.slsa_analyzer.provenance import intoto
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, InTotoV1Payload, InTotoV01Payload
from macaron.util import JsonType

logger: logging.Logger = logging.getLogger(__name__)


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
    """
    predicate_type = payload.statement.get("predicateType")
    if isinstance(payload, InTotoV1Payload):
        if isinstance(payload, InTotoV1Payload):
            if predicate_type == "https://slsa.dev/provenance/v1":
                return _extract_from_slsa_v1(payload)
    elif isinstance(payload, InTotoV01Payload):
        if predicate_type == "https://slsa.dev/provenance/v0.2":
            return _extract_from_slsa_v02(payload)
        if predicate_type == "https://slsa.dev/provenance/v0.1":
            return _extract_from_slsa_v01(payload)
        if predicate_type == "https://witness.testifysec.com/attestation-collection/v0.1":
            return _extract_from_witness_provenance(payload)

    logger.debug(
        "Extraction from provenance not supported for versions: predicate_type %s, in-toto %s.",
        predicate_type,
        payload.__class__,
    )
    return "", ""


def _extract_from_slsa_v01(payload: InTotoV01Payload) -> tuple[str, str]:
    """Extract the repository and commit metadata from the slsa v01 provenance payload."""
    predicate: dict[str, JsonType] | None = payload.statement.get("predicate")
    if not predicate:
        return "", ""

    # The repository URL and commit are stored inside an entry in the list of predicate -> materials.
    # In predicate -> recipe -> definedInMaterial we find the list index that points to the correct entry.
    list_index = _json_extract(predicate, ["recipe", "definedInMaterial"], int)
    if not list_index:
        return "", ""

    material_list = _json_extract(predicate, ["materials"], list)
    if not material_list:
        return "", ""

    if list_index >= len(material_list):
        return "", ""
    material = material_list[list_index]
    if not material or not isinstance(material, dict):
        return "", ""

    uri = material.get("uri")
    if not uri:
        logger.debug("Could not extract repository URL.")
    repo = _clean_spdx(uri)

    digest_set = material.get("digest")
    if not digest_set or not isinstance(digest_set, dict):
        return "", ""
    commit = _extract_commit_from_digest(digest_set)
    if not commit:
        logger.debug("Could not extract commit.")
        return "", ""

    return repo, commit


def _extract_from_slsa_v02(payload: InTotoV01Payload) -> tuple[str, str]:
    """Extract the repository and commit metadata from the slsa v02 provenance payload."""
    predicate: dict[str, JsonType] | None = payload.statement.get("predicate")
    if not predicate:
        return "", ""

    # The repository URL and commit are stored within the predicate -> invocation -> configSource object.
    # See https://slsa.dev/spec/v0.2/provenance
    uri = _json_extract(predicate, ["invocation", "configSource", "uri"], str)
    if not uri:
        logger.debug("Could not extract repo URL.")
        return "", ""
    repo = _clean_spdx(uri)

    digest_set = _json_extract(predicate, ["invocation", "configSource", "digest"], dict)
    if not digest_set:
        return "", ""
    commit = _extract_commit_from_digest(digest_set)
    if not commit:
        logger.debug("Could not extract commit.")
        return "", ""

    return repo, commit


def _extract_from_slsa_v1(payload: InTotoV1Payload) -> tuple[str, str]:
    """Extract the repository and commit metadata from the slsa v1 provenance payload."""
    predicate: dict[str, JsonType] | None = payload.statement.get("predicate")
    if not predicate:
        return "", ""

    build_def = _json_extract(predicate, ["buildDefinition"], dict)
    if not build_def:
        return "", ""
    build_type = _json_extract(build_def, ["buildType"], str)
    if not build_type:
        return "", ""

    # Extract the repository URL.
    repo = None
    if build_type == "https://slsa-framework.github.io/gcb-buildtypes/triggered-build/v1":
        repo = _json_extract(build_def, ["externalParameters", "sourceToBuild", "repository"], str)
        if not repo:
            repo = _json_extract(build_def, ["externalParameters", "configSource", "repository"], str)
    if build_type == "https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1":
        repo = _json_extract(build_def, ["externalParameters", "workflow", "repository"], str)

    if not repo:
        logger.debug("Failed to extract repository URL from provenance.")
        return "", ""

    # Extract the commit hash.
    commit = None
    deps = _json_extract(build_def, ["resolvedDependencies"], list)
    if not deps:
        return "", ""
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        uri = dep["uri"]
        url = _clean_spdx(uri)
        if url != repo:
            continue
        if build_type == "https://slsa-framework.github.io/gcb-buildtypes/triggered-build/v1":
            commit_dict = _json_extract(dep, ["digest"], dict)
            if not commit_dict:
                continue
            commit = _extract_commit_from_digest(commit_dict)
        if build_type == "https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1":
            commit = _json_extract(dep, ["digest", "gitCommit"], str)

    if not commit:
        logger.debug("Failed to extract commit hash from provenance.")
        return "", ""

    return repo, commit


def _extract_commit_from_digest(digest: dict[str, JsonType]) -> str | None:
    """Extract the commit from the passed DigestSet.

    The DigestSet is an in-toto object that maps algorithm types to commit hashes (digests).
    """
    # TODO decide on a preference for which algorithm to accept.
    if len(digest.keys()) > 1:
        logger.debug("DigestSet contains multiple algorithms: %s", digest.keys())

    for key in digest:
        if key in intoto.v1.VALID_ALGORITHMS:
            value = digest.get(key)
            if isinstance(value, str):
                return value
    return None


def _clean_spdx(uri: str) -> str:
    """Clean the passed SPDX URI and return the normalised URL it represents.

    A SPDX URI has the form: git+https://example.com@refs/heads/main
    """
    url, _, _ = uri.lstrip("git+").rpartition("@")
    return url


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
        return "", ""
    attestations = _json_extract(predicate, ["attestations"], list)
    if not attestations:
        return "", ""
    commit: str | None = None
    repo: str | None = None
    for entry in attestations:
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type")
        if not entry_type:
            continue
        if entry_type.startswith("https://witness.dev/attestations/git/"):
            commit = _json_extract(entry, ["attestation", "commithash"], str)
        elif entry_type.startswith("https://witness.dev/attestations/gitlab/") or entry_type.startswith(
            "https://witness.dev/attestations/github/"
        ):
            repo = _json_extract(entry, ["attestation", "projecturl"], str)

    if not commit or not repo:
        logger.debug("Could not extract repo and commit from provenance.")
        return "", ""

    return repo, commit


@overload
def _json_extract(entry: dict[str, JsonType], keys: list[str], type_: type[int]) -> int | None:
    ...


@overload
def _json_extract(entry: dict[str, JsonType], keys: list[str], type_: type[list]) -> list | None:
    ...


@overload
def _json_extract(entry: dict[str, JsonType], keys: list[str], type_: type[dict]) -> dict | None:
    ...


@overload
def _json_extract(entry: dict[str, JsonType], keys: list[str], type_: type[str]) -> str | None:
    ...


def _json_extract(entry: dict[str, JsonType], keys: list[str], type_: type[JsonType]) -> JsonType:
    """Return the value found by following the list of depth-sequential keys inside the passed dictionary.

    The value's type is validated against the passed type.
    """
    target = entry
    for index, key in enumerate(keys):
        if key not in target:
            logger.debug("Key not found in JSON: %s", key)
            return None
        next_target = target[key]
        if index == len(keys) - 1:
            if isinstance(next_target, type_):
                return next_target
        else:
            if not isinstance(next_target, dict):
                logger.debug("Expected dict found: %s", next_target.__class__)
                break
            target = next_target

    logger.debug("Failed to find %s in JSON dictionary", " > ".join(keys))
    return None
