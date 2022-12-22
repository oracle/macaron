# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This modules implements a check to verify a target repo has intoto provenance level 3."""

import glob
import hashlib
import logging
import os
import subprocess  # nosec B404
import tarfile
import tempfile
import zipfile
from pathlib import Path

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService, NoneCIService
from macaron.slsa_analyzer.git_url import get_repo_dir_name
from macaron.slsa_analyzer.provenance.loader import ProvPayloadLoader, SLSAProvenanceError
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


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

    def _size_large(self, asset_size: str) -> bool:
        """Check the size of the asset."""
        return int(asset_size) > defaults.getint("slsa.verifier", "max_download_size", fallback=1000000)

    def _verify_slsa(self, macaron_path: str, temp_path: str, prov_asset: dict, asset_name: str, url: str) -> str:
        """Run SLSA verifier to verify the artifact."""
        source_path = get_repo_dir_name(url, sanitize=False)
        if not source_path:
            logger.error("Invalid repository source path to verify: %s.", url)
            return ""

        feedback = ""
        errors: list[str] = []
        cmd = [
            os.path.join(macaron_path, "bin/slsa-verifier"),
            "verify-artifact",
            os.path.join(temp_path, asset_name),
            "--provenance-path",
            os.path.join(temp_path, prov_asset["name"]),
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
                feedback = f"{asset_name}."

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

        return feedback

    def _extract_archive(self, file_path: str, temp_path: str) -> bool:
        """Extract the archive file to the temporary path.

        Returns
        -------
        bool
            Returns True if successful.
        """
        try:
            if zipfile.is_zipfile(file_path):
                with zipfile.ZipFile(file_path, "r") as zip_file:
                    zip_file.extractall(temp_path)
                    return True
            elif tarfile.is_tarfile(file_path):
                with tarfile.open(file_path, mode="r:gz") as tar_file:
                    tar_file.extractall(temp_path)
                    return True
        except (
            tarfile.TarError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            OSError,
        ) as error:
            logger.info(error)

        return False

    def _find_asset(
        self, subject: dict, all_assets: list[dict[str, str]], temp_path: str, ci_service: BaseCIService
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
                logger.error("Error in check %s: %s", self.check_id, error)
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

    def run_check(self, ctx: AnalyzeContext, check_result: CheckResult) -> CheckResultType:
        """Implement the check in this method.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.
        check_result : CheckResult
            The object containing result data of a check.

        Returns
        -------
        CheckResultType
            The result type of the check (e.g. PASSED).
        """
        # TODO: During verification, we need to fetch the workflow and verify that it's not
        # using self-hosted runners, custom containers or services, etc.
        all_feedback = []
        ci_services = ctx.dynamic_data["ci_services"]
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
                        if self._size_large(prov_asset["size"]):
                            logger.info("Skip verifying the provenance %s: asset size too large.", prov_asset["name"])
                            continue

                        if not ci_service.api_client.download_asset(
                            prov_asset["url"], os.path.join(temp_path, prov_asset["name"])
                        ):
                            logger.info("Could not download the provenance %s. Skip verifying...", prov_asset["name"])
                            continue

                        # Read the provenance.
                        payload = ProvPayloadLoader.load(os.path.join(temp_path, prov_asset["name"]))

                        # Add the provenance file.
                        downloaded_provs.append(payload)

                        # Iterate through the subjects and verify.
                        for subject in payload["subject"]:
                            sub_asset = self._find_asset(subject, all_assets, temp_path, ci_service)

                            if not sub_asset:
                                logger.info("Could not find provenance subject %s. Skip verifying...", subject)
                                continue

                            if not Path(temp_path, sub_asset["name"]).is_file():
                                if "size" in sub_asset and self._size_large(sub_asset["size"]):
                                    logger.info(
                                        "Skip verifying the artifact %s: asset size too large.", sub_asset["name"]
                                    )
                                    continue

                                if "url" in sub_asset and not ci_service.api_client.download_asset(
                                    sub_asset["url"], os.path.join(temp_path, sub_asset["name"])
                                ):
                                    logger.info("Could not download artifact %s. Skip verifying...", sub_asset["name"])
                                    continue

                            feedback = self._verify_slsa(
                                ctx.macaron_path, temp_path, prov_asset, sub_asset["name"], ctx.remote_path
                            )
                            if not feedback:
                                logger.info("Could not verify SLSA Level three integrity for: %s.", sub_asset["name"])
                                continue

                            all_feedback.append(feedback)

                if downloaded_provs:
                    # Store the provenance available results for other checks.
                    # Note: this flag should only be turned off here.
                    ctx.dynamic_data["is_inferred_prov"] = False
                    ci_info["provenances"] = downloaded_provs

            except (OSError, SLSAProvenanceError) as error:
                logger.error(" %s: %s.", self.check_id, error)
                check_result["justification"].append("Could not verify level 3 provenance.")
                return CheckResultType.FAILED

        if all_feedback:
            check_result["justification"].append(
                "Successfully verified level 3 provenance for the following artifacts",
            )
            check_result["justification"].extend(all_feedback)
            return CheckResultType.PASSED
        check_result["justification"].append("Could not verify level 3 provenance.")
        return CheckResultType.FAILED


registry.register(ProvenanceL3Check())
