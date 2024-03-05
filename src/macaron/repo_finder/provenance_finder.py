# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains methods for finding provenance files."""
import logging
import os
import tempfile

from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.repo_finder.commit_finder import AbstractPurlType, determine_abstract_purl_type
from macaron.slsa_analyzer.checks.provenance_available_check import ProvenanceAvailableException
from macaron.slsa_analyzer.package_registry import JFrogMavenRegistry, NPMRegistry
from macaron.slsa_analyzer.package_registry.npm_registry import NPMAttestationAsset
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload
from macaron.slsa_analyzer.provenance.intoto.errors import LoadIntotoAttestationError
from macaron.slsa_analyzer.provenance.loader import load_provenance_payload
from macaron.slsa_analyzer.provenance.witness import is_witness_provenance_payload, load_witness_verifier_config

logger: logging.Logger = logging.getLogger(__name__)


class ProvenanceFinder:
    """This class is used to find and retrieve provenance files from supported registries."""

    def __init__(self) -> None:
        self.last_provenance_payload: InTotoPayload | None = None

    def find_provenance(self, purl: PackageURL) -> InTotoPayload | None:
        """Find the provenance files of the passed PURL.

        Parameters
        ----------
        purl: PackageURL
            The PURL to find provenance for.

        Returns
        -------
        InTotoPayload | None
            The provenance payload if found, or None.
        """
        if determine_abstract_purl_type(purl) == AbstractPurlType.REPOSITORY:
            # Do not perform this function for repository type targets.
            self.last_provenance_payload = None

        if purl.type == "npm":
            self.last_provenance_payload = ProvenanceFinder.find_npm_provenance(purl)
        elif purl.type in ["gradle", "maven"]:
            self.last_provenance_payload = ProvenanceFinder.find_gav_provenance(purl)
        else:
            logger.debug("Provenance finding not supported for PURL type: %s", purl.type)
            self.last_provenance_payload = None

        return self.last_provenance_payload

    @staticmethod
    def find_npm_provenance(purl: PackageURL) -> InTotoPayload | None:
        """Find and download the NPM based provenance for the passed PURL.

        Parameters
        ----------
        purl: PackageURL
            The PURL of the analysis target.

        Returns
        -------
        InTotoPayload | None
            The provenance payload if found, or None.
        """
        # Retrieve NPM registry configuration values.
        npm_section = "package_registry.npm"
        if not defaults.has_section(npm_section):
            logger.debug("No NPM section found in config.")
            return None
        if not defaults.get(npm_section, "enabled"):
            logger.debug("NPM section disabled in config.")
            return None

        hostname = defaults.get(npm_section, "hostname")
        attestation_endpoint = defaults.get(npm_section, "attestation_endpoint")
        try:
            request_timeout = int(defaults.get(npm_section, "request_timeout"))
        except ValueError as error:
            logger.debug("Invalid value for NPM package registry timeout: %s", error)
            return None
        # Create registry from configuration values.
        npm_registry = NPMRegistry(hostname, attestation_endpoint, request_timeout)

        namespace = purl.namespace or ""
        artifact_id = purl.name
        version = purl.version

        if not purl.version:
            version = npm_registry.get_latest_version(namespace, artifact_id)

        if not version:
            logger.debug("Missing version for NPM package.")
            return None

        # The size of the asset (in bytes) is added to match the AssetLocator
        # protocol and is not used because npm API registry does not provide it, so it is set to zero.
        npm_provenance_asset = NPMAttestationAsset(
            namespace=namespace,
            artifact_id=artifact_id,
            version=version,
            npm_registry=npm_registry,
            size_in_bytes=0,
        )
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                download_path = os.path.join(temp_dir, f"{artifact_id}.intoto.jsonl")
                if not npm_provenance_asset.download(download_path):
                    logger.debug("Unable to find an npm provenance for %s@%s", artifact_id, version)
                    return None

                try:
                    # Load the provenance file.
                    provenance_payload = load_provenance_payload(download_path)
                except LoadIntotoAttestationError as loadintotoerror:
                    logger.error("Error while loading provenance %s", loadintotoerror)
                    return None

                return provenance_payload
        except OSError as error:
            logger.error("Error while storing provenance in the temporary directory: %s", error)
            return None

    @staticmethod
    def find_gav_provenance(purl: PackageURL) -> InTotoPayload | None:
        """Find and download the GAV based provenance for the passed PURL.

        Parameters
        ----------
        purl: PackageURL
            The PURL of the analysis target.

        Returns
        -------
        InTotoPayload | None
            The provenance payload if found, or None.

        """
        jfrog_section = "package_registry.jfrog.maven"
        if not defaults.has_section(jfrog_section):
            logger.debug("No JFrog section found in config.")
            return None

        try:
            request_timeout = defaults.getint(jfrog_section, "request_timeout")
            download_timeout = defaults.getint(jfrog_section, "download_timeout")
        except ValueError as error:
            logger.debug("Failed to parse default value as int: %s", error)
            return None

        jfrog_registry = JFrogMavenRegistry(
            defaults.get(jfrog_section, "hostname"),
            defaults.get(jfrog_section, "repo"),
            request_timeout,
            download_timeout,
        )

        provenance_extensions = defaults.get_list(
            "slsa.verifier",
            "provenance_extensions",
            fallback=["intoto.jsonl"],
        )

        provenance_assets = jfrog_registry.fetch_assets(
            group_id=purl.namespace if purl.namespace else "",
            artifact_id=purl.name,
            version=purl.version if purl.version else "",
            extensions=set(provenance_extensions),
        )

        if not provenance_assets:
            return None

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
            return None

        # TODO decide what to do when multiple provenance payloads are present.
        provenance = provenances[0]

        return provenance
