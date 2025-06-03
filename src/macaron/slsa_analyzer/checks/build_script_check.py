# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildScriptCheck class."""

import logging
import os

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.database.table_definitions import CheckFacts
from macaron.errors import CallGraphError
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService, NoneCIService
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class BuildScriptFacts(CheckFacts):
    """The ORM mapping for justifications in build_script check."""

    __tablename__ = "_build_script_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The name of the tool used to build.
    build_tool_name: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The CI service name used to build and deploy.
    ci_service_name: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The entrypoint script that triggers the build and deploy.
    build_trigger: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

    #: The language of the artifact built by build tool command.
    language: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The possible language distributions.
    language_distributions: Mapped[str | None] = mapped_column(
        String, nullable=True, info={"justification": JustificationType.TEXT}
    )

    #: The possible language versions.
    language_versions: Mapped[str | None] = mapped_column(
        String, nullable=True, info={"justification": JustificationType.TEXT}
    )

    #: The URL that provides information about the language distribution and version.
    language_url: Mapped[str | None] = mapped_column(
        String, nullable=True, info={"justification": JustificationType.HREF}
    )

    #: The build tool command.
    build_tool_command: Mapped[str] = mapped_column(
        String, nullable=True, info={"justification": JustificationType.TEXT}
    )

    __mapper_args__ = {
        "polymorphic_identity": "_build_script_check",
    }


class BuildScriptCheck(BaseCheck):
    """This Check checks whether the target repo has a valid build script."""

    def __init__(self) -> None:
        """Initiate the BuildScriptCheck instance."""
        check_id = "mcn_build_script_1"
        description = "Check if the target repo has a valid build script."
        depends_on: list[tuple[str, CheckResultType]] = [("mcn_version_control_system_1", CheckResultType.PASSED)]
        eval_reqs = [ReqName.SCRIPTED_BUILD]
        super().__init__(
            check_id=check_id,
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.FAILED,
        )

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
        build_tools = ctx.dynamic_data["build_spec"]["tools"]

        if not build_tools:
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        # Check if any build tools are discovered for this repo.
        # TODO: look for build commands in the bash scripts. Currently
        #       we parse bash scripts that are reachable through CI only.
        result_tables: list[CheckFacts] = []
        ci_services = ctx.dynamic_data["ci_services"]
        for tool in build_tools:
            for ci_info in ci_services:
                ci_service: BaseCIService = ci_info["service"]
                # Checking if a CI service is discovered for this repo.
                if isinstance(ci_service, NoneCIService):
                    continue
                try:
                    for build_command in ci_service.get_build_tool_commands(
                        callgraph=ci_info["callgraph"], build_tool=tool
                    ):
                        trigger_link = ci_service.api_client.get_file_link(
                            ctx.component.repository.full_name,
                            ctx.component.repository.commit_sha,
                            ci_service.api_client.get_relative_path_of_workflow(
                                os.path.basename(build_command["ci_path"])
                            ),
                        )
                        result_tables.append(
                            BuildScriptFacts(
                                build_tool_name=tool.name,
                                ci_service_name=ci_service.name,
                                build_trigger=trigger_link,
                                language=build_command["language"],
                                language_distributions=(
                                    tool.serialize_to_json(build_command["language_distributions"])
                                    if build_command["language_distributions"]
                                    else None
                                ),
                                language_versions=(
                                    tool.serialize_to_json(build_command["language_versions"])
                                    if build_command["language_versions"]
                                    else None
                                ),
                                language_url=build_command["language_url"],
                                build_tool_command=tool.serialize_to_json(build_command["command"]),
                                confidence=Confidence.HIGH,
                            )
                        )
                except CallGraphError as error:
                    logger.debug(error)

        return CheckResultData(result_tables=result_tables, result_type=CheckResultType.PASSED)


registry.register(BuildScriptCheck())
