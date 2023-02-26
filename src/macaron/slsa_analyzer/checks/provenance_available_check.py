# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the implementation of the Provenance Available check."""

import logging
import re

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.config.defaults import defaults
from macaron.database.database_manager import ORMBase
from macaron.database.table_definitions import CheckFactsTable
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.ci_service.base_ci_service import NoneCIService
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


def is_in_toto_file(file_name: str) -> bool:
    """Return true if the file name matches the in-toto file format.

    The format for those files is ``<stage_name>.<6_bytes_key_id>.link``.

    Parameters
    ----------
    file_name : str
        The name of the file to check.

    Returns
    -------
    bool
    """
    in_toto_format = re.compile(r"\w+\.[0-9a-f]{6}\.link$")
    if in_toto_format.match(file_name):
        return True

    return False


class ProvenanceAvailableTable(CheckFactsTable, ORMBase):
    """Check justification table for provenance_available."""

    __tablename__ = "_provenance_available_check"
    asset_name: Mapped[str] = mapped_column(String)
    asset_url: Mapped[str] = mapped_column(String)


class ProvenanceAvailableCheck(BaseCheck):
    """This Check checks whether the target repo has in-toto provenance."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_provenance_available_1"
        description = "Check whether the target has intoto provenance."
        depends_on: list[tuple[str, CheckResultType]] = []
        eval_reqs = [
            ReqName.PROV_AVAILABLE,
            ReqName.PROV_CONT_BUILD_INS,
            ReqName.PROV_CONT_ARTI,
            ReqName.PROV_CONT_BUILDER,
        ]
        super().__init__(check_id=check_id, description=description, depends_on=depends_on, eval_reqs=eval_reqs)

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
        ci_services = ctx.dynamic_data["ci_services"]
        for ci_info in ci_services:
            ci_service = ci_info["service"]
            # Checking if a CI service is discovered for this repo.
            if isinstance(ci_service, NoneCIService):
                continue
            # Only get the latest release.
            release = ci_service.api_client.get_latest_release(ctx.repo_full_name)
            if release:
                # Store the release data for other checks.
                ci_info["latest_release"] = release

                # Get the provenance assets.
                for prov_ext in defaults.get_list("slsa.verifier", "provenance_extensions"):
                    assets = ci_service.api_client.get_assets(release, ext=prov_ext)
                    if not assets:
                        continue

                    # Store the provenance assets for other checks.
                    ci_info["provenance_assets"].extend(assets)

                    check_result["justification"].append("Found provenance in release assets:")
                    check_result["justification"].extend([asset["name"] for asset in assets])
                    asset_results = [
                        {
                            "asset_name": asset["name"],
                            "asset_url": asset["url"],
                        }
                        for asset in assets
                    ]
                    check_result["result_tables"] = [ProvenanceAvailableTable(**res) for res in asset_results]

                    return CheckResultType.PASSED

            else:
                logger.info("Could not find any release for %s in the repository.", ci_service.name)
        check_result["justification"].append("Could not find any SLSA provenances.")
        return CheckResultType.FAILED


registry.register(ProvenanceAvailableCheck())
