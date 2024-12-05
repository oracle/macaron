# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements a check to verify the timestamp difference between commit finder and the latest version in Maven."""

import logging
from datetime import datetime
from datetime import timedelta

from sqlalchemy import ForeignKey, String, Interval
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.database.db_custom_types import RFC3339DateTime
from macaron.errors import InvalidHTTPResponseError
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.package_registry.maven_central_registry import MavenCentralRegistry
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


class TimestampCheckFacts(CheckFacts):
    """The ORM mapping for justifications in timestamp check."""

    __tablename__ = "_timestamp_check"

    # The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The package name.
    package_name: Mapped[str] = mapped_column(String, nullable=False)

    #: The commit finder date.
    commit_finder_date: Mapped[datetime] = mapped_column(RFC3339DateTime, nullable=False)

    #: The latest timestamp from Maven.
    latest_timestamp: Mapped[datetime] = mapped_column(RFC3339DateTime, nullable=False)

    #: The time difference.
    time_difference: Mapped[Interval] = mapped_column(Interval, nullable=False, info={"justification": JustificationType.TEXT})

    #: The latest version.
    latest_version: Mapped[str] = mapped_column(String, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "_timestamp_check",
    }


class TimestampCheck(BaseCheck):
    """This Check verifies the timestamp difference between commit finder and the latest version in Maven."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_timestamp_check_1"
        description = "Check timestamp difference between commit finder and latest version in Maven."
        depends_on: list[tuple[str, CheckResultType]] = []
        eval_reqs = [ReqName.VCS]
        super().__init__(check_id=check_id, description=description, depends_on=depends_on, eval_reqs=eval_reqs)

    def run_check(self, ctx: AnalyzeContext) -> CheckResultData:
        """Implement the check in this method.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.

        Returns
        -------
        CheckResultData
            The result type of the check.
        """
        # Get the commit date from Macaron's commit finder
        commit_finder_date = ctx.component.repository.commit_date
        if not commit_finder_date:
            logger.info("No commit date found for the component.")
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        # Look for the artifact in the corresponding registry and find the publish timestamp.
        artifact_published_date = None
        package_registry_info_entries = ctx.dynamic_data["package_registries"]
        for package_registry_info_entry in package_registry_info_entries:
            match package_registry_info_entry:
                case PackageRegistryInfo(
                    build_tool=Maven(),
                    package_registry=MavenCentralRegistry() as mvn_central_registry,
                ):
                    group_id = ctx.component.namespace
                    artifact_id = ctx.component.name
                    version = ctx.component.version
                    try:
                        artifact_published_date = mvn_central_registry.find_publish_timestamp(
                            group_id, artifact_id, version
                        )
                    except InvalidHTTPResponseError as error:
                        logger.debug(error)

        if not artifact_published_date:
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        # Compare timestamps
        time_difference = artifact_published_date - commit_finder_date
        package_name = f"{ctx.component.namespace}/{ctx.component.name}"

        result_facts = TimestampCheckFacts(
            package_name=package_name,
            commit_finder_date=commit_finder_date,
            latest_timestamp=artifact_published_date,
            time_difference=time_difference,
            latest_version=ctx.component.version,
            confidence=Confidence.HIGH
        )

        if time_difference > timedelta(hours=24):
            return CheckResultData(result_tables=[result_facts], result_type=CheckResultType.PASSED)
        else:
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)


registry.register(TimestampCheck())