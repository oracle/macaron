# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains methods for finding provenance files."""
import logging
import os
import tempfile
from collections.abc import Callable
from inspect import signature
from typing import Any

from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.repo_finder.commit_finder import AbstractPurlType, determine_abstract_purl_type
from macaron.slsa_analyzer.checks.provenance_available_check import ProvenanceAvailableException
from macaron.slsa_analyzer.package_registry import PACKAGE_REGISTRIES, JFrogMavenRegistry, NPMRegistry
from macaron.slsa_analyzer.package_registry.npm_registry import NPMAttestationAsset
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload
from macaron.slsa_analyzer.provenance.intoto.errors import LoadIntotoAttestationError
from macaron.slsa_analyzer.provenance.loader import load_provenance_payload
from macaron.slsa_analyzer.provenance.witness import is_witness_provenance_payload, load_witness_verifier_config

logger: logging.Logger = logging.getLogger(__name__)


class ProvenanceFinder:
    """This class is used to find and retrieve provenance files from supported registries."""

    def __init__(self) -> None:
        registries = PACKAGE_REGISTRIES
        self.npm_registry: NPMRegistry | None = None
        self.jfrog_registry: JFrogMavenRegistry | None = None
        if registries:
            for registry in registries:
                if isinstance(registry, NPMRegistry):
                    self.npm_registry = registry
                elif isinstance(registry, JFrogMavenRegistry):
                    self.jfrog_registry = registry

    def find_provenance(
        self,
        purl: PackageURL,
        discovery_functions: list[Callable[..., list[InTotoPayload]]] | None = None,
        parameter_lists: list[list[Any]] | None = None,
    ) -> list[InTotoPayload]:
        """Find the provenance file(s) of the passed PURL.

        Parameters
        ----------
        purl: PackageURL
            The PURL to find provenance for.
        discovery_functions: list[Callable[..., list[InTotoPayload]]] | None
            A list of discovery functions to use for the given PURL, or None if the default should be used instead.
        parameter_lists: list[Any] | None
            The lists of parameters to pass to the callables, or None if the default should be used instead.

        Returns
        -------
        list[InTotoPayload]
            The provenance payload, or an empty list if not found.
        """
        if not discovery_functions:
            if determine_abstract_purl_type(purl) == AbstractPurlType.REPOSITORY:
                # Do not perform default discovery for repository type targets.
                return []

            if purl.type == "npm":
                if not self.npm_registry:
                    logger.debug("Missing npm registry to find provenance in.")
                    return []
                discovery_functions = [find_npm_provenance]
                parameter_lists = [[purl, self.npm_registry]]

            elif purl.type in ["gradle", "maven"]:
                if self.jfrog_registry:
                    discovery_functions = [find_gav_provenance]
                    parameter_lists = [[purl, self.jfrog_registry]]
                logger.debug("Missing JFrog registry to find provenance in.")
            else:
                logger.debug("Provenance finding not supported for PURL type: %s", purl.type)

        if not discovery_functions:
            logger.debug("No provenance discovery functions provided/found for %s", purl)
            return []

        for index, discovery_function in enumerate(discovery_functions):
            parameter_list = parameter_lists[index] if parameter_lists and index < len(parameter_lists) else [purl]
            function_signature = signature(discovery_function)
            if len(function_signature.parameters) != len(parameter_list):
                logger.debug(
                    "Mismatch between function and parameters: %s vs. %s",
                    len(function_signature.parameters),
                    len(parameter_list),
                )
                continue

            provenance = discovery_function(*parameter_list)

            if provenance:
                return provenance

        logger.debug("No provenance found.")
        return []

    def verify_provenance(
        self,
        purl: PackageURL,
        provenance: list[InTotoPayload],
        verification_function: Callable[[PackageURL, list[InTotoPayload]], bool] | None = None,
        parameters: list[Any] | None = None,
    ) -> bool:
        """Verify the passed provenance.

        Parameters
        ----------
        purl: PackageURL
            The PURL of the analysis target.
        provenance: list[InTotoPayload]
            The list of provenance.
        verification_function: list[Callable[[PackageURL, list[InTotoPayload]], bool]] | None
            A callable that should verify the provenance, or None if the default callable should be used instead.
        parameters: list[Any] | None
            The list of parameters to pass to the callable, or None.

        Returns
        -------
        bool
            True if the provenance could be verified, or False otherwise.
        """
        if not verification_function:
            if determine_abstract_purl_type(purl) == AbstractPurlType.REPOSITORY:
                # Do not perform default verification for repository type targets.
                return False

            if purl.type == "npm":
                verification_function = verify_npm_provenance
                parameters = [purl, provenance]
            else:
                logger.debug("Provenance verification not supported for PURL type: %s", purl.type)

        if not verification_function:
            logger.debug("No provenance verification function provided/found for %s", purl)
            return False

        if not parameters:
            logger.debug("No parameter arguments for provenance verification function.")
            return False

        provenance_verified = verification_function(*parameters)

        if not provenance_verified:
            logger.debug("Provenance could not be verified.")
        return provenance_verified


def find_npm_provenance(purl: PackageURL, registry: NPMRegistry) -> list[InTotoPayload]:
    """Find and download the NPM based provenance for the passed PURL.

    Two kinds of attestation can be retrieved from npm: "Provenance" and "Publish". The "Provenance" attestation
    contains the important information Macaron seeks, but is not signed. The "Publish" attestation is signed.
    Comparison of the signed vs unsigned at the subject level, allows the unsigned to be verified.
    See: https://docs.npmjs.com/generating-provenance-statements

    Parameters
    ----------
    purl: PackageURL
        The PURL of the analysis target.
    registry: NPMRegistry
        The npm registry to use.

    Returns
    -------
    list[InTotoPayload]
        The provenance payload(s), or an empty list if not found.
    """
    if not registry.enabled:
        logger.debug("The npm registry is not enabled.")
        return []

    namespace = purl.namespace
    artifact_id = purl.name
    version = purl.version

    if not purl.version:
        version = registry.get_latest_version(namespace, artifact_id)

    if not version:
        logger.debug("Missing version for NPM package.")
        return []

    # The size of the asset (in bytes) is added to match the AssetLocator
    # protocol and is not used because npm API registry does not provide it, so it is set to zero.
    npm_provenance_asset = NPMAttestationAsset(
        namespace=namespace,
        artifact_id=artifact_id,
        version=version,
        npm_registry=registry,
        size_in_bytes=0,
    )
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            download_path = os.path.join(temp_dir, f"{artifact_id}.intoto.jsonl")
            if not npm_provenance_asset.download(download_path):
                logger.debug("Unable to find an npm provenance for %s@%s", artifact_id, version)
                return []

            try:
                # Load the provenance file (provenance attestation).
                provenance_payload = load_provenance_payload(download_path)
            except LoadIntotoAttestationError as error:
                logger.error("Error while loading provenance attestation: %s", error)
                return []

            signed_download_path = f"{download_path}.signed"
            try:
                # Load the other npm provenance file (publish attestation).
                publish_payload = load_provenance_payload(signed_download_path)
            except LoadIntotoAttestationError as error:
                logger.error("Error while loading publish attestation: %s", error)
                return [provenance_payload]

            return [provenance_payload, publish_payload]

    except OSError as error:
        logger.error("Error while storing provenance in the temporary directory: %s", error)
        return []


def verify_npm_provenance(purl: PackageURL, provenance: list[InTotoPayload]) -> bool:
    """Compare the unsigned payload subject digest with the signed payload digest, if available.

    Parameters
    ----------
    purl: PackageURL
        The PURL of the analysis target.
    provenance: list[InTotoPayload]
        The provenances to verify.

    Returns
    -------
    bool
        True if the provenance was verified, or False otherwise.
    """
    if len(provenance) != 2:
        logger.debug("Expected unsigned and signed provenance.")
        return False

    signed_subjects = provenance[1].statement.get("subject")
    if not signed_subjects:
        return False

    unsigned_subjects = provenance[0].statement.get("subject")
    if not unsigned_subjects:
        return False

    found_signed_subject = None
    for signed_subject in signed_subjects:
        name = signed_subject.get("name")
        if name and name == str(purl):
            found_signed_subject = signed_subject
            break

    if not found_signed_subject:
        return False

    found_unsigned_subject = None
    for unsigned_subject in unsigned_subjects:
        name = unsigned_subject.get("name")
        if name and name == str(purl):
            found_unsigned_subject = unsigned_subject
            break

    if not found_unsigned_subject:
        return False

    signed_digest = found_signed_subject.get("digest")
    unsigned_digest = found_unsigned_subject.get("digest")
    if not (signed_digest and unsigned_digest):
        return False

    # For signed and unsigned to match, the digests must be identical.
    if signed_digest != unsigned_digest:
        return False

    key = list(signed_digest.keys())[0]
    logger.debug(
        "Verified provenance against signed companion. Signed: %s, Unsigned: %s.",
        signed_digest[key][:7],
        unsigned_digest[key][:7],
    )

    return True


def find_gav_provenance(purl: PackageURL, registry: JFrogMavenRegistry) -> list[InTotoPayload]:
    """Find and download the GAV based provenance for the passed PURL.

    Parameters
    ----------
    purl: PackageURL
        The PURL of the analysis target.
    registry: JFrogMavenRegistry
        The registry to use for finding.

    Returns
    -------
    list[InTotoPayload] | None
        The provenance payload if found, or an empty list otherwise.

    Raises
    ------
    ProvenanceAvailableException
        If the discovered provenance file size exceeds the configured limit.
    """
    if not registry.enabled:
        logger.debug("JFrog registry not enabled.")
        return []

    if not purl.namespace or not purl.version:
        logger.debug("Missing purl namespace or version for finding provenance in JFrog registry.")
        return []

    provenance_extensions = defaults.get_list(
        "slsa.verifier",
        "provenance_extensions",
        fallback=["intoto.jsonl"],
    )

    provenance_assets = registry.fetch_assets(
        group_id=purl.namespace,
        artifact_id=purl.name,
        version=purl.version,
        extensions=set(provenance_extensions),
    )

    if not provenance_assets:
        return []

    max_valid_provenance_size = defaults.getint(
        "slsa.verifier",
        "max_download_size",
        fallback=1000000,
    )

    for provenance_asset in provenance_assets:
        if provenance_asset.size_in_bytes > max_valid_provenance_size:
            msg = (
                f"The provenance asset {provenance_asset.name} unexpectedly exceeds the "
                f"max valid file size of {max_valid_provenance_size} (bytes). "
                "The check will not proceed due to potential security risks."
            )
            logger.error(msg)
            raise ProvenanceAvailableException(msg)

    provenance_filepaths = []
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            for provenance_asset in provenance_assets:
                provenance_filepath = os.path.join(temp_dir, provenance_asset.name)
                if not provenance_asset.download(provenance_filepath):
                    logger.debug(
                        "Could not download the provenance %s. Skip verifying...",
                        provenance_asset.name,
                    )
                    continue
                provenance_filepaths.append(provenance_filepath)
    except OSError as error:
        logger.error("Error while storing provenance in the temporary directory: %s", error)

    provenances = []
    witness_verifier_config = load_witness_verifier_config()

    for provenance_filepath in provenance_filepaths:
        try:
            provenance_payload = load_provenance_payload(provenance_filepath)
        except LoadIntotoAttestationError as error:
            logger.error("Error while loading provenance: %s", error)
            continue

        if not is_witness_provenance_payload(provenance_payload, witness_verifier_config.predicate_types):
            continue

        provenances.append(provenance_payload)

    if not provenances:
        logger.debug("No payloads found in provenance files.")
        return []

    # We assume that there is only one provenance per GAV.
    return provenances[:1]
