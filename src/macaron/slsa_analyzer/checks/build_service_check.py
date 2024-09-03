# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildServiceCheck class."""

import logging
import os

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.database.table_definitions import CheckFacts
from macaron.errors import CallGraphError
from macaron.slsa_analyzer.analyze_context import AnalyzeContext, store_inferred_build_info_results
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService, NoneCIService
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class BuildServiceFacts(CheckFacts):
    """The ORM mapping for justifications in build_service check."""

    __tablename__ = "_build_service_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The name of the tool used to build.
    build_tool_name: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The CI service name used to build.
    ci_service_name: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The entrypoint script that triggers the build.
    build_trigger: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

    #: The command used to build.
    build_command: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.TEXT})

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

    __mapper_args__ = {
        "polymorphic_identity": "_build_service_check",
    }


class BuildServiceCheck(BaseCheck):
    """This Check checks whether the target repo has a valid build service."""

    def __init__(self) -> None:
        """Initiate the BuildServiceCheck instance."""
        check_id = "mcn_build_service_1"
        description = "Check if the target repo has a valid build service."
        depends_on: list[tuple[str, CheckResultType]] = [("mcn_build_as_code_1", CheckResultType.FAILED)]
        eval_reqs = [ReqName.BUILD_SERVICE]
        super().__init__(
            check_id=check_id,
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.PASSED,
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
        # Get the build tool identified by the mcn_version_control_system_1, which we depend on.
        build_tools = ctx.dynamic_data["build_spec"]["tools"]

        if not build_tools:
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        ci_services = ctx.dynamic_data["ci_services"]

        # Check if "build as code" holds for each build tool.
        overall_res = CheckResultType.FAILED

        result_tables: list[CheckFacts] = []
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
                        # Yes or no with a confidence score.
                        result, confidence = tool.is_package_command(
                            build_command, ci_service.get_third_party_configurations()
                        )
                        if result:
                            trigger_link = ci_service.api_client.get_file_link(
                                ctx.component.repository.full_name,
                                ctx.component.repository.commit_sha,
                                ci_service.api_client.get_relative_path_of_workflow(
                                    os.path.basename(build_command["ci_path"])
                                ),
                            )
                            # Store or update the inferred provenance if the confidence
                            # for the current check fact is bigger than the maximum score.
                            if (
                                not result_tables
                                or confidence > max(result_tables, key=lambda item: item.confidence).confidence
                            ):
                                store_inferred_build_info_results(
                                    ctx=ctx, ci_info=ci_info, ci_service=ci_service, trigger_link=trigger_link
                                )
                            result_tables.append(
                                BuildServiceFacts(
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
                                    build_command=tool.serialize_to_json(build_command["command"]),
                                    confidence=confidence,
                                )
                            )
                            overall_res = CheckResultType.PASSED
                except CallGraphError as error:
                    logger.debug(error)

                # We currently don't parse these CI configuration files.
                # We just look for a keyword for now.
                for unparsed_ci in (Jenkins, Travis, CircleCI, GitLabCI):
                    if isinstance(ci_service, unparsed_ci):
                        if tool.ci_build_kws[ci_service.name]:
                            build_kw, config_name = ci_service.has_kws_in_config(
                                tool.ci_build_kws[ci_service.name],
                                build_tool_name=tool.name,
                                repo_path=ctx.component.repository.fs_path,
                            )
                            if not config_name:
                                break

                            store_inferred_build_info_results(
                                ctx=ctx, ci_info=ci_info, ci_service=ci_service, trigger_link=config_name
                            )
                            result_tables.append(
                                BuildServiceFacts(
                                    build_tool_name=tool.name,
                                    language=tool.language.value,
                                    ci_service_name=ci_service.name,
                                    build_command=build_kw,
                                    confidence=Confidence.LOW,
                                )
                            )
                            overall_res = CheckResultType.PASSED

        # The check passing is contingent on at least one passing, if
        # one passes treat whole check as passing. We do still need to
        # run the others for justifications though to report multiple
        # build tool usage.
        # TODO: When more sophisticated build tool detection is
        # implemented, consider whether this should be one fail = whole
        # check fails instead

        return CheckResultData(result_tables=result_tables, result_type=overall_res)


registry.register(BuildServiceCheck())
