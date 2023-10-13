# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This modules implements a check to verify a target repo has intoto provenance level 3."""

import glob
import hashlib
import json
import logging
import os
import subprocess  # nosec B404
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.database.table_definitions import CheckFacts, HashDigest, Provenance, ReleaseArtifact
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.asset import AssetLocator
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Justification, ResultTables
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService, NoneCIService
from macaron.slsa_analyzer.git_url import get_repo_dir_name
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload, v01
from macaron.slsa_analyzer.provenance.intoto.errors import InTotoAttestationError, UnsupportedInTotoVersionError
from macaron.slsa_analyzer.provenance.loader import load_provenance_payload
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class _VerifyArtifactResultType(Enum):
    """Result of attempting to verify an asset."""

    # slsa-verifier succeeded and the artifact passed verification
    PASSED = "verify passed"
    # slsa-verifier succeeded and the artifact failed verification
    FAILED = "verify failed"
    # An error occurred running slsa-verifier or downloading the artifact
    ERROR = "verify error"
    # The artifact was unable to be downloaded because the url was missing or malformed
    NO_DOWNLOAD = "unable to download asset"
    # The artifact was unable to be downloaded because the file was too large
    TOO_LARGE = "asset file too large to download"

    def is_skip(self) -> bool:
        """Return whether the verification was skipped."""
        return self in (_VerifyArtifactResultType.NO_DOWNLOAD, _VerifyArtifactResultType.TOO_LARGE)

    def is_fail(self) -> bool:
        """Return whether the verification failed."""
        return self in (_VerifyArtifactResultType.FAILED, _VerifyArtifactResultType.ERROR)


@dataclass
class _VerifyArtifactResult:
    """Dataclass storing the result of verifying a single asset."""

    result: _VerifyArtifactResultType
    artifact_name: str

    def __str__(self) -> str:
        return f"{str(self.result.value)} : {self.artifact_name}"


class ProvenanceResultFacts(CheckFacts):
    """The ORM mapping for justifications in provenance_l3 check."""

    __tablename__ = "_provenance_l3_check"

    # The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    __mapper_args__ = {
        "polymorphic_identity": "_provenance_l3_check",
    }


class ProvenanceL3Check(BaseCheck):
    """This Check checks whether the target repo has SLSA provenance level 3."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_provenance_level_three_1"
        description = "Check whether the target has SLSA provenance level 3."
        depends_on: list[tuple[str, CheckResultType]] = [("mcn_provenance_available_1", CheckResultType.PASSED)]

        # SLSA 3: only identifies the top-level build config and not all the build inputs (hermetic).
        # TODO: revisit if ReqName.PROV_CONT_SOURCE should be here or not. That's because the definition
        # of source is not clear. See https://github.com/slsa-framework/slsa/issues/465.
        eval_reqs = [
            ReqName.PROV_NON_FALSIFIABLE,
            ReqName.PROV_CONT_BUILD_PARAMS,
            ReqName.PROV_CONT_ENTRY,
            ReqName.PROV_CONT_SOURCE,
        ]
        super().__init__(
            check_id=check_id,
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.FAILED,
        )

    def _size_large(self, asset_size: int) -> bool:
        """Check the size of the asset."""
        return asset_size > defaults.getint("slsa.verifier", "max_download_size", fallback=1000000)

    def _verify_slsa(
        self, macaron_path: str, temp_path: str, prov_asset: AssetLocator, asset_name: str, repository_url: str
    ) -> _VerifyArtifactResult:
        """Run SLSA verifier to verify the artifact."""
        source_path = get_repo_dir_name(repository_url, sanitize=False)
        if not source_path:
            logger.error("Invalid repository source path to verify: %s.", repository_url)
            return _VerifyArtifactResult(_VerifyArtifactResultType.NO_DOWNLOAD, asset_name)

        errors: list[str] = []
        result: _VerifyArtifactResult
        cmd = [
            os.path.join(macaron_path, "bin/slsa-verifier"),
            "verify-artifact",
            os.path.join(temp_path, asset_name),
            "--provenance-path",
            os.path.join(temp_path, prov_asset.name),
            "--source-uri",
            source_path,
        ]

        try:
            verifier_output = subprocess.run(  # nosec B603
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True,
                cwd=temp_path,
                timeout=defaults.getint("slsa.verifier", "timeout", fallback=120),
            )

            output = verifier_output.stdout.decode("utf-8")
            if "PASSED: Verified SLSA provenance" in output:
                result = _VerifyArtifactResult(_VerifyArtifactResultType.PASSED, asset_name)
            else:
                result = _VerifyArtifactResult(_VerifyArtifactResultType.FAILED, asset_name)

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
            result = _VerifyArtifactResult(result=_VerifyArtifactResultType.ERROR, artifact_name=asset_name)
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

        return result

    def _extract_archive(self, file_path: str, temp_path: str) -> bool:
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

    def _find_asset(
        self,
        subject: v01.InTotoV01Subject,
        all_assets: list[dict[str, str]],
        temp_path: str,
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

        extracted_artifact = glob.glob(os.path.join(temp_path, "**", os.path.basename(subject["name"])), recursive=True)
        for artifact_path in extracted_artifact:
            try:
                with open(artifact_path, "rb") as file:
                    if hashlib.sha256(file.read()).hexdigest() == subject["digest"]["sha256"]:
                        return {"name": str(Path(artifact_path).relative_to(temp_path))}
            except OSError as error:
                logger.error("Error in check %s: %s", self.check_info.check_id, error)
                continue

        for item in all_assets:
            item_path = os.path.join(temp_path, item["name"])
            # Make sure to download an archive just once.
            if not Path(item_path).is_file():
                # TODO: check that it's not too large.
                if not ci_service.api_client.download_asset(item["url"], item_path):
                    logger.info("Could not download artifact %s. Skip verifying...", os.path.basename(item_path))
                    break

                if self._extract_archive(file_path=item_path, temp_path=temp_path):
                    return self._find_asset(subject, all_assets, temp_path, ci_service)

        return None

    def run_check(self, ctx: AnalyzeContext) -> CheckResultData:
        """Implement the check in this method.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.

        Returns
        -------
        CheckResultData
            The result of the check.
        """
        # TODO: During verification, we need to fetch the workflow and verify that it's not
        # using self-hosted runners, custom containers or services, etc.

        class Feedback(NamedTuple):
            """Store feedback item."""

            ci_service_name: str
            asset_url: str
            verify_result: _VerifyArtifactResult

        all_feedback: list[Feedback] = []
        ci_services = ctx.dynamic_data["ci_services"]

        justification: Justification = []
        result_tables: ResultTables = []

        result_tables = [ProvenanceResultFacts()]
        for ci_info in ci_services:
            ci_service = ci_info["service"]

            # Checking if a CI service is discovered for this repo.
            if isinstance(ci_service, NoneCIService):
                continue

            # Checking if we have found a release for the repo.
            if not ci_info["latest_release"] or "assets" not in ci_info["latest_release"]:
                logger.info("Could not find any release assets for the repository.")
                break

            # Checking if we have found a SLSA provenance for the repo.
            if not ci_info["provenance_assets"]:
                logger.info("Could not find SLSA provenances.")
                break

            prov_assets = ci_info["provenance_assets"]
            all_assets = ci_info["latest_release"]["assets"]

            # Download and verify the artifacts if they are not large.
            # Create a temporary directory and automatically remove it when we are done.
            try:
                with tempfile.TemporaryDirectory() as temp_path:
                    downloaded_provs = []
                    for prov_asset in prov_assets:
                        # Check the size before downloading.
                        if self._size_large(prov_asset.size_in_bytes):
                            logger.info("Skip verifying the provenance %s: asset size too large.", prov_asset.name)
                            continue

                        if not ci_service.api_client.download_asset(
                            prov_asset.url, os.path.join(temp_path, prov_asset.name)
                        ):
                            logger.info("Could not download the provenance %s. Skip verifying...", prov_asset.name)
                            continue

                        # Read the provenance.
                        provenance_payload = load_provenance_payload(
                            os.path.join(temp_path, prov_asset.name),
                        )

                        if not isinstance(provenance_payload, InTotoV01Payload):
                            raise UnsupportedInTotoVersionError(
                                f"The provenance asset '{prov_asset.name}' is under an unsupported in-toto version."
                            )

                        # Add the provenance file.
                        downloaded_provs.append(provenance_payload.statement)

                        # Output provenance
                        prov = Provenance()
                        # TODO: fix commit reference for provenance when release/artifact as an analysis entrypoint is
                        #  implemented ensure the provenance commit matches the actual release analyzed
                        prov.version = "0.2"
                        prov.release_commit_sha = ""
                        prov.provenance_json = json.dumps(provenance_payload.statement)
                        prov.release_tag = ci_info["latest_release"]["tag_name"]
                        prov.component = ctx.component

                        result_tables.append(prov)

                        # Iterate through the subjects and verify.
                        for subject in provenance_payload.statement["subject"]:
                            sub_asset = self._find_asset(subject, all_assets, temp_path, ci_service)

                            result: None | _VerifyArtifactResult = None
                            for _ in range(1):
                                if not sub_asset:
                                    result = _VerifyArtifactResult(
                                        result=_VerifyArtifactResultType.NO_DOWNLOAD, artifact_name=subject["name"]
                                    )
                                    break
                                if not Path(temp_path, sub_asset["name"]).is_file():
                                    if "size" in sub_asset and self._size_large(sub_asset["size"]):
                                        result = _VerifyArtifactResult(
                                            result=_VerifyArtifactResultType.TOO_LARGE,
                                            artifact_name=sub_asset["name"],
                                        )
                                        break
                                    if "url" in sub_asset and not ci_service.api_client.download_asset(
                                        sub_asset["url"], os.path.join(temp_path, sub_asset["name"])
                                    ):
                                        result = _VerifyArtifactResult(
                                            result=_VerifyArtifactResultType.NO_DOWNLOAD,
                                            artifact_name=sub_asset["name"],
                                        )
                                        break

                                result = self._verify_slsa(
                                    ctx.macaron_path,
                                    temp_path,
                                    prov_asset,
                                    sub_asset["name"],
                                    ctx.component.repository.remote_path,
                                )

                            if result:
                                if result.result.is_skip():
                                    logger.info("Skipped verifying artifact: %s", result.result)
                                if result.result.is_fail():
                                    logger.info("Error verifying artifact: %s", result.result)
                                if result.result == _VerifyArtifactResultType.FAILED:
                                    logger.info("Failed verifying artifact: %s", result.result)
                                if result.result == _VerifyArtifactResultType.PASSED:
                                    logger.info("Successfully verified artifact: %s", result.result)

                                all_feedback.append(
                                    Feedback(
                                        ci_service_name=ci_service.name,
                                        asset_url=prov_asset.url,
                                        verify_result=result,
                                    )
                                )

                                # Store artifact information result to database.
                                artifact = ReleaseArtifact()
                                artifact.name = subject["name"]
                                artifact.slsa_verified = result.result == _VerifyArtifactResultType.PASSED
                                artifact.provenance = prov  # pylint: disable=protected-access
                                result_tables.append(artifact)

                                for k, val in subject["digest"].items():
                                    digest = HashDigest()
                                    digest.digest_algorithm = k
                                    digest.digest = val
                                    # foreign key relations
                                    digest.artifact = artifact
                                    result_tables.append(digest)

            except (OSError, InTotoAttestationError) as error:
                logger.error(" %s: %s.", self.check_info.check_id, error)
                justification.append("Could not verify level 3 provenance.")
                return CheckResultData(
                    justification=justification, result_tables=result_tables, result_type=CheckResultType.FAILED
                )

        result_value = CheckResultType.FAILED
        if all_feedback:
            all_results = [feedback.verify_result for feedback in all_feedback]
            failed = [
                result
                for ci_name, prov_url, result in all_feedback
                if result.result == _VerifyArtifactResultType.FAILED
            ]
            passed = [
                result
                for ci_name, prov_url, result in all_feedback
                if result.result == _VerifyArtifactResultType.PASSED
            ]
            skipped = [
                result for ci_name, prov_url, result in all_feedback if result not in passed and result not in failed
            ]

            if failed or skipped:
                justification.append("Failed verification for level 3: ")
                result_value = CheckResultType.FAILED
            else:
                justification.append("Successfully verified level 3: ")
                result_value = CheckResultType.PASSED

            justification.append(",".join(map(str, all_results)))
            return CheckResultData(justification=justification, result_tables=result_tables, result_type=result_value)

        justification.append("Could not verify level 3 provenance.")
        return CheckResultData(justification=justification, result_tables=result_tables, result_type=result_value)


registry.register(ProvenanceL3Check())
