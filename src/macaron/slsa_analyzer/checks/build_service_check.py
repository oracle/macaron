# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildServiceCheck class."""

import json
import logging
import os
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.ci_service.base_ci_service import NoneCIService
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName
from macaron.slsa_analyzer.specs.ci_spec import CIInfo

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

    #: The run status of the CI service for this build.
    build_status_url: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

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

    def _serialize_command(self, cmd: list[str]) -> str:
        """Convert a list of command-line arguments to a json-encoded string so that it is easily parsable by later consumers.

        Parameters
        ----------
        cmd: list[str]
            List of command-line arguments.

        Returns
        -------
        str
            The list of command-line arguments as a json-encoded string.
        """
        return json.dumps(cmd)

    def _has_build_command(self, commands: list[list[str]], build_tool: BaseBuildTool) -> str:
        """Check if the bash command is a build command."""
        for com in commands:
            # Check for empty or invalid commands.
            if not com or not com[0]:
                continue
            # The first argument in a bash command is the program name.
            # So first check that the program name is a supported build tool name.
            # We need to handle cases where the first argument is a path to the program.
            cmd_program_name = os.path.basename(com[0])
            if not cmd_program_name:
                logger.debug("Found invalid program name %s.", com[0])
                continue

            builder = build_tool.packager if build_tool.packager else build_tool.builder

            check_build_commands = any(build_cmd for build_cmd in builder if build_cmd == cmd_program_name)

            # Support the use of interpreters like Python that load modules, i.e., 'python -m pip install'.
            check_module_build_commands = any(
                interpreter == cmd_program_name
                and com[1]
                and com[1] in build_tool.interpreter_flag
                and com[2]
                and com[2] in builder
                for interpreter in build_tool.interpreter
            )

            prog_name_index = 2 if check_module_build_commands else 0

            if check_build_commands or check_module_build_commands:
                # Check the arguments in the bash command for the build goals.
                # If there are no build args for this build tool, accept as build command.
                # TODO: Support multi-argument build keywords, issue #493.
                if not build_tool.build_arg:
                    com_str = self._serialize_command(com)
                    logger.info("No build arguments required. Accept %s as build command.", com_str)
                    return com_str
                for word in com[(prog_name_index + 1) :]:
                    # TODO: allow plugin versions in arguments, e.g., maven-plugin:1.6.8:package.
                    if word in build_tool.build_arg:
                        com_str = self._serialize_command(com)
                        logger.info("Found build command %s.", com_str)
                        return com_str
        return ""

    def _check_build_tool(
        self,
        build_tool: BaseBuildTool,
        ctx: AnalyzeContext,
        ci_services: list[CIInfo],
        result_tables: list[CheckFacts],
    ) -> CheckResultType:
        """
        Check that a single build tool has a build service associated to it.

        Parameters
        ----------
        build_tool : BaseBuildTool
            Build tool to analyse for
        ctx : AnalyzeContext
            The object containing processed data for the target repo.
        ci_services: list[CIInfo]
            List of objects containing information on present CI services.
        result_tables: ResultTables
            List of result tables to add to.

        Returns
        -------
        CheckResultType
            The result type of the check (e.g. PASSED).
        """
        for ci_info in ci_services:
            ci_service = ci_info["service"]
            # Checking if a CI service is discovered for this repo.
            if isinstance(ci_service, NoneCIService):
                continue
            for bash_cmd in ci_info["bash_commands"]:
                build_cmd = self._has_build_command(bash_cmd["commands"], build_tool)
                if build_cmd:
                    # Get the permalink and HTML hyperlink tag of the CI file that triggered the bash command.
                    trigger_link = ci_service.api_client.get_file_link(
                        ctx.component.repository.full_name,
                        ctx.component.repository.commit_sha,
                        ci_service.api_client.get_relative_path_of_workflow(os.path.basename(bash_cmd["CI_path"])),
                    )
                    # Get the permalink and HTML hyperlink tag of the source file of the bash command.
                    bash_source_link = ci_service.api_client.get_file_link(
                        ctx.component.repository.full_name, ctx.component.repository.commit_sha, bash_cmd["caller_path"]
                    )

                    html_url = ci_service.has_latest_run_passed(
                        ctx.component.repository.full_name,
                        ctx.component.repository.branch_name,
                        ctx.component.repository.commit_sha,
                        ctx.component.repository.commit_date,
                        os.path.basename(bash_cmd["CI_path"]),
                    )

                    result_tables.append(
                        BuildServiceFacts(
                            build_tool_name=build_tool.name,
                            build_trigger=trigger_link,
                            build_command=build_cmd,
                            ci_service_name=ci_service.name,
                            confidence=Confidence.HIGH,
                        )
                    )

                    if (
                        ctx.dynamic_data["is_inferred_prov"]
                        and ci_info["provenances"]
                        and isinstance(ci_info["provenances"][0].payload, InTotoV01Payload)
                    ):
                        predicate: Any = ci_info["provenances"][0].payload.statement["predicate"]
                        predicate["buildType"] = f"Custom {ci_service.name}"
                        predicate["builder"]["id"] = bash_source_link
                        predicate["invocation"]["configSource"]["uri"] = (
                            f"{ctx.component.repository.remote_path}"
                            f"@refs/heads/{ctx.component.repository.branch_name}"
                        )
                        predicate["invocation"]["configSource"]["digest"]["sha1"] = ctx.component.repository.commit_sha
                        predicate["invocation"]["configSource"]["entryPoint"] = trigger_link
                        predicate["metadata"]["buildInvocationId"] = html_url
                    return CheckResultType.PASSED

            # We currently don't parse these CI configuration files.
            # We just look for a keyword for now.
            for unparsed_ci in (Jenkins, Travis, CircleCI, GitLabCI):
                if isinstance(ci_service, unparsed_ci):
                    if build_tool.ci_build_kws[ci_service.name]:
                        _, config_name = ci_service.has_kws_in_config(
                            build_tool.ci_build_kws[ci_service.name], repo_path=ctx.component.repository.fs_path
                        )
                        if not config_name:
                            break

                        result_tables.append(
                            BuildServiceFacts(
                                build_tool_name=build_tool.name,
                                ci_service_name=ci_service.name,
                                confidence=Confidence.MEDIUM,
                            )
                        )

                        if (
                            ctx.dynamic_data["is_inferred_prov"]
                            and ci_info["provenances"]
                            and isinstance(ci_info["provenances"][0].payload, InTotoV01Payload)
                        ):
                            predicate = ci_info["provenances"][0].payload.statement["predicate"]
                            predicate["buildType"] = f"Custom {ci_service.name}"
                            predicate["builder"]["id"] = config_name
                            predicate["invocation"]["configSource"]["uri"] = (
                                f"{ctx.component.repository.remote_path}"
                                f"@refs/heads/{ctx.component.repository.branch_name}"
                            )
                            predicate["invocation"]["configSource"]["digest"][
                                "sha1"
                            ] = ctx.component.repository.commit_sha
                            predicate["invocation"]["configSource"]["entryPoint"] = config_name
                        return CheckResultType.PASSED

        # Nothing found; fail.
        return CheckResultType.FAILED

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
        ci_services = ctx.dynamic_data["ci_services"]

        # Checking if at least one build tool is discovered for this repo.
        # No build tools is auto fail.
        # TODO: When more sophisticated build tool detection is
        # implemented, consider whether this should be one fail = whole
        # check fails instead
        all_passing = False
        result_tables: list[CheckFacts] = []

        for tool in build_tools:
            res = self._check_build_tool(tool, ctx, ci_services, result_tables)

            if res == CheckResultType.PASSED:
                # Pass at some point so treat as entire check pass; we don't
                # short-circuit for the sake of full justification reporting
                # though.
                all_passing = True

        if not all_passing or not build_tools:
            return CheckResultData(result_tables=result_tables, result_type=CheckResultType.FAILED)

        return CheckResultData(result_tables=result_tables, result_type=CheckResultType.PASSED)


registry.register(BuildServiceCheck())
