# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains methods for finding provenance files."""
import logging
import os
import tempfile
from functools import partial

from packageurl import PackageURL
from pydriller import Git

from macaron.config.defaults import defaults
from macaron.repo_finder.commit_finder import AbstractPurlType, determine_abstract_purl_type
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.provenance_available_check import ProvenanceAvailableException
from macaron.slsa_analyzer.ci_service import GitHubActions
from macaron.slsa_analyzer.ci_service.base_ci_service import NoneCIService
from macaron.slsa_analyzer.package_registry import PACKAGE_REGISTRIES, JFrogMavenRegistry, NPMRegistry
from macaron.slsa_analyzer.package_registry.npm_registry import NPMAttestationAsset
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload
from macaron.slsa_analyzer.provenance.intoto.errors import LoadIntotoAttestationError
from macaron.slsa_analyzer.provenance.loader import load_provenance_payload
from macaron.slsa_analyzer.provenance.slsa import SLSAProvenanceData
from macaron.slsa_analyzer.provenance.witness import is_witness_provenance_payload, load_witness_verifier_config
from macaron.slsa_analyzer.specs.ci_spec import CIInfo

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

    def find_provenance(self, purl: PackageURL) -> list[InTotoPayload]:
        """Find the provenance file(s) of the passed PURL.

        Parameters
        ----------
        purl: PackageURL
            The PURL to find provenance for.

        Returns
        -------
        list[InTotoPayload]
            The provenance payload, or an empty list if not found.
        """
        logger.debug("Seeking provenance of: %s", purl)

        if determine_abstract_purl_type(purl) == AbstractPurlType.REPOSITORY:
            # Do not perform default discovery for repository type targets.
            return []

        if purl.type == "npm":
            if not self.npm_registry:
                logger.debug("Missing npm registry to find provenance in.")
                return []

            discovery_functions = [partial(find_npm_provenance, purl, self.npm_registry)]
            return self._find_provenance(discovery_functions)

        if purl.type in {"gradle", "maven"}:
            # TODO add support for Maven Central provenance.
            if not self.jfrog_registry:
                logger.debug("Missing JFrog registry to find provenance in.")
                return []

            discovery_functions = [partial(find_gav_provenance, purl, self.jfrog_registry)]
            return self._find_provenance(discovery_functions)

        # TODO add other possible discovery functions.
        logger.debug("Provenance finding not supported for PURL type: %s", purl.type)
        return []

    def _find_provenance(self, discovery_functions: list[partial[list[InTotoPayload]]]) -> list[InTotoPayload]:
        """Find the provenance file(s) using the passed discovery functions.

        Parameters
        ----------
        discovery_functions: list[partial[list[InTotoPayload]]]
            A list of discovery functions to use to find the provenance.

        Returns
        -------
        list[InTotoPayload]
            The provenance payload(s) from the first successful function, or an empty list if none were.
        """
        if not discovery_functions:
            return []

        for discovery_function in discovery_functions:
            provenance = discovery_function()

            if provenance:
                return provenance

        logger.debug("No provenance found.")
        return []

    def verify_provenance(self, purl: PackageURL, provenance: list[InTotoPayload]) -> bool:
        """Verify the passed provenance.

        Parameters
        ----------
        purl: PackageURL
            The PURL of the analysis target.
        provenance: list[InTotoPayload]
            The list of provenance.

        Returns
        -------
        bool
            True if the provenance could be verified, or False otherwise.
        """
        if determine_abstract_purl_type(purl) == AbstractPurlType.REPOSITORY:
            # Do not perform default verification for repository type targets.
            return False

        verification_function = None

        if purl.type == "npm":
            verification_function = partial(verify_npm_provenance, purl, provenance)

        # TODO other verification functions go here.

        if verification_function:
            return verification_function()

        logger.debug("Provenance verification not supported for PURL type: %s", purl.type)
        return False


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

    provenances = []
    witness_verifier_config = load_witness_verifier_config()
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

                try:
                    provenance_payload = load_provenance_payload(provenance_filepath)
                except LoadIntotoAttestationError as load_error:
                    logger.error("Error while loading provenance: %s", load_error)
                    continue

                if not is_witness_provenance_payload(provenance_payload, witness_verifier_config.predicate_types):
                    continue

                provenances.append(provenance_payload)
    except OSError as error:
        logger.error("Error while storing provenance in the temporary directory: %s", error)

    if not provenances:
        logger.debug("No payloads found in provenance files.")
        return []

    # We assume that there is only one provenance per GAV.
    return provenances[:1]


def find_provenance_from_ci(analyze_ctx: AnalyzeContext, git_obj: Git | None) -> InTotoPayload | None:
    """Try to find provenance from CI services of the repository.

    Note that we stop going through the CI services once we encounter a CI service
    that does host provenance assets.

    This method also loads the provenance payloads into the ``CIInfo`` object where
    the provenance assets are found.

    Parameters
    ----------
    analyze_ctx: AnalyzeContext
        The contenxt of the ongoing analysis.
    git_obj: Git | None
        The Pydriller Git object representing the repository, if any.

    Returns
    -------
    InTotoPayload | None
        The provenance payload, or None if not found.
    """
    provenance_extensions = defaults.get_list(
        "slsa.verifier",
        "provenance_extensions",
        fallback=["intoto.jsonl"],
    )
    component = analyze_ctx.component
    ci_info_entries = analyze_ctx.dynamic_data["ci_services"]

    if not component.repository:
        logger.debug("Unable to find a provenance because a repository was not found for %s.", component.purl)
        return None

    repo_full_name = component.repository.full_name
    for ci_info in ci_info_entries:
        ci_service = ci_info["service"]

        if isinstance(ci_service, NoneCIService):
            continue

        if isinstance(ci_service, GitHubActions):
            # Find the release for the software component version being analyzed.
            digest = component.repository.commit_sha
            tag = None
            if git_obj:
                # Use the software component commit to find the tag.
                if not digest:
                    logger.debug("Cannot retrieve asset provenance without commit digest.")
                    return None
                tags = git_obj.repo.tags
                for _tag in tags:
                    try:
                        tag_commit = str(_tag.commit)
                    except ValueError as error:
                        logger.debug("Commit of tag is a blob or tree: %s", error)
                        continue
                    if tag_commit and tag_commit == digest:
                        tag = str(_tag)
                        break

            if not tag:
                logger.debug("Could not find the tag matching commit: %s", digest)
                return None

            # Get the correct release using the tag.
            release_payload = ci_service.api_client.get_release_by_tag(repo_full_name, tag)
            if not release_payload:
                logger.debug("Failed to find release matching tag: %s", tag)
                return None

            # Store the release data for other checks.
            ci_info["release"] = release_payload

            # Get the provenance assets.
            for prov_ext in provenance_extensions:
                provenance_assets = ci_service.api_client.fetch_assets(
                    release_payload,
                    ext=prov_ext,
                )
                if not provenance_assets:
                    continue

                logger.info("Found the following provenance assets:")
                for provenance_asset in provenance_assets:
                    logger.info("* %s", provenance_asset.url)

                # Store the provenance assets for other checks.
                ci_info["provenance_assets"].extend(provenance_assets)

                # Download the provenance assets and load the provenance payloads.
                download_provenances_from_github_actions_ci_service(
                    ci_info,
                )

                # TODO consider how to handle multiple payloads here.
                return ci_info["provenances"][0].payload if ci_info["provenances"] else None

        else:
            logger.debug("CI service not supported for provenance finding: %s", ci_service.name)

    return None


def download_provenances_from_github_actions_ci_service(ci_info: CIInfo) -> None:
    """Download provenances from GitHub Actions.

    Parameters
    ----------
    ci_info: CIInfo,
        A ``CIInfo`` instance that holds a GitHub Actions git service object.
    """
    ci_service = ci_info["service"]
    prov_assets = ci_info["provenance_assets"]

    try:
        with tempfile.TemporaryDirectory() as temp_path:
            downloaded_provs = []
            for prov_asset in prov_assets:
                # Check the size before downloading.
                if prov_asset.size_in_bytes > defaults.getint(
                    "slsa.verifier",
                    "max_download_size",
                    fallback=1000000,
                ):
                    logger.info(
                        "Skip verifying the provenance %s: asset size too large.",
                        prov_asset.name,
                    )
                    continue

                provenance_filepath = os.path.join(temp_path, prov_asset.name)

                if not ci_service.api_client.download_asset(
                    prov_asset.url,
                    provenance_filepath,
                ):
                    logger.debug(
                        "Could not download the provenance %s. Skip verifying...",
                        prov_asset.name,
                    )
                    continue

                # Read the provenance.
                try:
                    payload = load_provenance_payload(provenance_filepath)
                except LoadIntotoAttestationError as error:
                    logger.error("Error logging provenance: %s", error)
                    continue

                # Add the provenance file.
                downloaded_provs.append(SLSAProvenanceData(payload=payload, asset=prov_asset))

            # Persist the provenance payloads into the CIInfo object.
            ci_info["provenances"] = downloaded_provs
    except OSError as error:
        logger.error("Error while storing provenance in the temporary directory: %s", error)
