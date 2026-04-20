# Copyright (c) 2024 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the LicenseCheck class."""

import logging
import os
import re

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.config.defaults import defaults
from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.git_service.github import GitHub
from macaron.slsa_analyzer.registry import registry

logger: logging.Logger = logging.getLogger(__name__)


def _find_license_file(fs_path: str) -> str | None:
    """Return the path to the first license file found in the root of ``fs_path``, or ``None``.

    Parameters
    ----------
    fs_path : str
        The path to the root of the cloned repository on the local filesystem.

    Returns
    -------
    str | None
        Absolute path to the license file if found, otherwise ``None``.
    """
    pattern = defaults.get(
        "license",
        "license_filename_pattern",
        fallback=r"(LICENSE|LICENCE|COPYING)(\.md|\.txt|\.rst)?",
    )
    try:
        regex = re.compile(pattern, flags=re.IGNORECASE)
    except re.error as err:
        logger.error("Invalid regex pattern for license_filename_pattern: %s (%s)", pattern, err)
        return None

    try:
        for name in os.listdir(fs_path):
            if regex.fullmatch(name):
                candidate = os.path.join(fs_path, name)
                if os.path.isfile(candidate):
                    return candidate
    except OSError as err:
        logger.debug("Failed to list directory %s: %s", fs_path, err)

    return None


class LicenseFacts(CheckFacts):
    """The ORM mapping for justifications in the license check."""

    __tablename__ = "_license_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The SPDX identifier of the detected license (e.g. ``MIT``).
    spdx_id: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.TEXT})

    #: The human-readable license name (e.g. ``MIT License``).
    license_name: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.TEXT})

    #: The source of the license detection: ``github_api`` or ``filesystem``.
    license_source: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.TEXT})

    #: The URL to the license file on GitHub.
    license_url: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

    __mapper_args__ = {
        "polymorphic_identity": "_license_check",
    }


class LicenseCheck(BaseCheck):
    """Check whether the repository license is in the configured allow-list."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_license_1"
        description = "Check whether the repository license is in the configured allow-list."
        super().__init__(check_id=check_id, description=description)

    def run_check(self, ctx: AnalyzeContext) -> CheckResultData:
        """Implement the check.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.

        Returns
        -------
        CheckResultData
            The result of the check.
        """
        allowed_list = defaults.get_list("license", "allowed_licenses", fallback=[])
        require_license = defaults.getboolean("license", "require_license", fallback=False)

        # Only supported for GitHub repositories.
        git_service = ctx.dynamic_data["git_service"]
        if not isinstance(git_service, GitHub):
            logger.debug("License check is not supported for non-GitHub repositories.")
            return CheckResultData(result_tables=[], result_type=CheckResultType.UNKNOWN)

        if not getattr(ctx.component, "repository", None):
            logger.debug("No repository found for %s.", ctx.component.purl)
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        full_name = f"{ctx.component.repository.owner}/{ctx.component.repository.name}"
        fs_path = ctx.component.repository.fs_path

        # Attempt license detection via GitHub API.
        spdx_id: str | None = None
        license_name: str | None = None
        license_url: str | None = None
        license_source: str | None = None

        response = git_service.api_client.get_license(full_name)
        license_data = response.get("license", {})
        api_spdx_id = license_data.get("spdx_id")

        if api_spdx_id and api_spdx_id != "NOASSERTION":
            spdx_id = api_spdx_id
            license_name = license_data.get("name")
            license_url = response.get("html_url")
            license_source = "github_api"
            logger.debug("License detected via GitHub API for %s: %s", full_name, spdx_id)
        else:
            # Fall back to scanning the cloned filesystem.
            found_file = _find_license_file(fs_path)
            if found_file:
                license_name = os.path.basename(found_file)
                license_source = "filesystem"
                logger.debug("License file found on filesystem for %s: %s", full_name, license_name)
            else:
                logger.debug("No license detected for %s.", full_name)

        # Determine result.
        if spdx_id is None:
            if require_license:
                logger.debug("No license detected for %s and require_license is True.", full_name)
                result_type = CheckResultType.FAILED
            else:
                logger.debug("No license detected for %s.", full_name)
                result_type = CheckResultType.PASSED
            confidence = Confidence.LOW
        elif not allowed_list:
            logger.debug("License %s detected for %s (all licenses allowed).", spdx_id, full_name)
            result_type = CheckResultType.PASSED
            confidence = Confidence.HIGH
        elif spdx_id in allowed_list:
            logger.debug("License %s is in the allow-list for %s.", spdx_id, full_name)
            result_type = CheckResultType.PASSED
            confidence = Confidence.HIGH
        else:
            logger.debug("License %s is not in the allow-list for %s.", spdx_id, full_name)
            result_type = CheckResultType.FAILED
            confidence = Confidence.HIGH

        return CheckResultData(
            result_tables=[
                LicenseFacts(
                    confidence=confidence,
                    spdx_id=spdx_id,
                    license_name=license_name,
                    license_source=license_source,
                    license_url=license_url,
                )
            ],
            result_type=result_type,
        )


registry.register(LicenseCheck())
