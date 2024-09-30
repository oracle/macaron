# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains methods for verifying provenance files."""
import glob
import hashlib
import logging
import os
import subprocess  # nosec B404
import tarfile
import zipfile
from functools import partial
from pathlib import Path

from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.repo_finder.commit_finder import AbstractPurlType, determine_abstract_purl_type
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.asset import AssetLocator
from macaron.slsa_analyzer.ci_service import BaseCIService
from macaron.slsa_analyzer.git_url import get_repo_dir_name
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, InTotoV01Payload, v01
from macaron.slsa_analyzer.specs.ci_spec import CIInfo

logger: logging.Logger = logging.getLogger(__name__)


def verify_provenance(purl: PackageURL, provenance: list[InTotoPayload]) -> bool:
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


def verify_ci_provenance(analyze_ctx: AnalyzeContext, ci_info: CIInfo, download_path: str) -> bool:
    """Try to verify the CI provenance in terms of SLSA level 3 requirements.

    Involves running the SLSA verifier.

    Parameters
    ----------
    analyze_ctx: AnalyzeContext
        The context of the analysis.
    ci_info: CIInfo
        A ``CIInfo`` instance that holds a GitHub Actions git service object.
    download_path: str
        The location to search for downloaded files.

    Returns
    -------
    bool
        True if the provenance could be verified.
    """
    # TODO: During verification, we need to fetch the workflow and verify that it's not
    # using self-hosted runners, custom containers or services, etc.
    ci_service = ci_info["service"]
    for provenance in ci_info["provenances"]:
        if not isinstance(provenance.payload, InTotoV01Payload):
            logger.debug("Cannot verify provenance type: %s", type(provenance.payload))
            continue

        all_assets = ci_info["release"]["assets"]

        # Iterate through the subjects and verify.
        for subject in provenance.payload.statement["subject"]:
            sub_asset = _find_subject_asset(subject, all_assets, download_path, ci_service)

            if not sub_asset:
                logger.debug("Sub asset not found for: %s.", provenance.payload.statement["subject"])
                return False
            if not Path(download_path, sub_asset["name"]).is_file():
                if "size" in sub_asset and sub_asset["size"] > defaults.getint(
                    "slsa.verifier", "max_download_size", fallback=1000000
                ):
                    logger.debug("Sub asset too large to verify: %s", sub_asset["name"])
                    return False
                if "url" in sub_asset and not ci_service.api_client.download_asset(
                    sub_asset["url"], os.path.join(download_path, sub_asset["name"])
                ):
                    logger.debug("Sub asset not found: %s", sub_asset["name"])
                    return False

            sub_verified = _verify_slsa(
                analyze_ctx.macaron_path,
                download_path,
                provenance.asset,
                sub_asset["name"],
                analyze_ctx.component.repository.remote_path,
            )

            if not sub_verified:
                return False

            if sub_verified:
                logger.info("Successfully verified sub asset: %s", sub_asset["name"])

    return True


def _find_subject_asset(
    subject: v01.InTotoV01Subject,
    all_assets: list[dict[str, str]],
    download_path: str,
    ci_service: BaseCIService,
) -> dict | None:
    """Find the artifacts that appear in the provenance subject.

    The artifacts can be directly found as a release asset or in an archive file.
    """
    sub_asset = next(
        (item for item in all_assets if item["name"] == os.path.basename(subject["name"])),
        None,
    )

    if sub_asset:
        return sub_asset

    extracted_artifact = glob.glob(os.path.join(download_path, "**", os.path.basename(subject["name"])), recursive=True)
    for artifact_path in extracted_artifact:
        try:
            with open(artifact_path, "rb") as file:
                if hashlib.sha256(file.read()).hexdigest() == subject["digest"]["sha256"]:
                    return {"name": str(Path(artifact_path).relative_to(download_path))}
        except OSError as error:
            logger.error("Error in check: %s", error)
            continue

    for item in all_assets:
        item_path = os.path.join(download_path, item["name"])
        # Make sure to download an archive just once.
        if not Path(item_path).is_file():
            # TODO: check that it's not too large.
            if not ci_service.api_client.download_asset(item["url"], item_path):
                logger.info("Could not download artifact %s. Skip verifying...", os.path.basename(item_path))
                break

            if _extract_archive(file_path=item_path, temp_path=download_path):
                return _find_subject_asset(subject, all_assets, download_path, ci_service)

    return None


def _extract_archive(file_path: str, temp_path: str) -> bool:
    """Extract the archive file to the temporary path.

    Returns
    -------
    bool
        Returns True if successful.
    """

    def _validate_path_traversal(path: str) -> bool:
        """Check for path traversal attacks."""
        if path.startswith("/") or ".." in path:
            logger.debug("Found suspicious path in the archive file: %s.", path)
            return False
        try:
            # Check if there are any symbolic links.
            if os.path.realpath(path):
                return True
        except OSError as error:
            logger.debug("Failed to extract artifact from archive file: %s", error)
            return False
        return False

    try:
        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, "r") as zip_file:
                members = (path for path in zip_file.namelist() if _validate_path_traversal(path))
                zip_file.extractall(temp_path, members=members)  # nosec B202:tarfile_unsafe_members
                return True
        elif tarfile.is_tarfile(file_path):
            with tarfile.open(file_path, mode="r:gz") as tar_file:
                members_tarinfo = (
                    tarinfo for tarinfo in tar_file.getmembers() if _validate_path_traversal(tarinfo.name)
                )
                tar_file.extractall(temp_path, members=members_tarinfo)  # nosec B202:tarfile_unsafe_members
                return True
    except (tarfile.TarError, zipfile.BadZipFile, zipfile.LargeZipFile, OSError, ValueError) as error:
        logger.info(error)

    return False


def _verify_slsa(
    macaron_path: str, download_path: str, prov_asset: AssetLocator, asset_name: str, repository_url: str
) -> bool:
    """Run SLSA verifier to verify the artifact."""
    source_path = get_repo_dir_name(repository_url, sanitize=False)
    if not source_path:
        logger.error("Invalid repository source path to verify: %s.", repository_url)
        return False

    errors: list[str] = []
    verified = False
    cmd = [
        os.path.join(macaron_path, "bin/slsa-verifier"),
        "verify-artifact",
        os.path.join(download_path, asset_name),
        "--provenance-path",
        os.path.join(download_path, prov_asset.name),
        "--source-uri",
        source_path,
    ]

    try:
        verifier_output = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
            cwd=download_path,
            timeout=defaults.getint("slsa.verifier", "timeout", fallback=120),
        )

        output = verifier_output.stdout.decode("utf-8")
        verified = "PASSED: Verified SLSA provenance" in output

        log_path = os.path.join(global_config.build_log_path, f"{os.path.basename(source_path)}.slsa_verifier.log")
        with open(log_path, mode="a", encoding="utf-8") as log_file:
            logger.info("Storing SLSA verifier output for %s to %s", asset_name, log_path)
            log_file.writelines(
                [f"SLSA verifier output for cmd: {' '.join(cmd)}\n", output, "--------------------------------\n"]
            )

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        logger.error(error)
        errors.append(error.output.decode("utf-8"))
    except OSError as error:
        logger.error(error)
        errors.append(str(error))

    if errors:
        verified = False
        try:
            error_log_path = os.path.join(
                global_config.build_log_path, f"{os.path.basename(source_path)}.slsa_verifier.errors"
            )
            with open(error_log_path, mode="a", encoding="utf-8") as log_file:
                logger.info("Storing SLSA verifier log for%s to %s", asset_name, error_log_path)
                log_file.write(f"SLSA verifier output for cmd: {' '.join(cmd)}\n")
                log_file.writelines(errors)
                log_file.write("--------------------------------\n")
        except OSError as error:
            logger.error(error)

    return verified
