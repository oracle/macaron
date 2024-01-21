# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildAsCodeCheck class."""

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
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Justification, ResultTables
from macaron.slsa_analyzer.ci_service.base_ci_service import NoneCIService
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.github_actions import GHWorkflowType
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName
from macaron.slsa_analyzer.specs.ci_spec import CIInfo

logger: logging.Logger = logging.getLogger(__name__)


class BuildAsCodeFacts(CheckFacts):
    """The ORM mapping for justifications in build_as_code check."""

    __tablename__ = "_build_as_code_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The name of the tool used to build.
    build_tool_name: Mapped[str] = mapped_column(String, nullable=False)

    #: The CI service name used to build and deploy.
    ci_service_name: Mapped[str] = mapped_column(String, nullable=False)

    #: The entrypoint script that triggers the build and deploy.
    build_trigger: Mapped[str] = mapped_column(String, nullable=True)

    #: The command used to deploy.
    deploy_command: Mapped[str] = mapped_column(String, nullable=True)

    #: The run status of the CI service for this build.
    build_status_url: Mapped[str] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "_build_as_code_check",
    }


class BuildAsCodeCheck(BaseCheck):
    """This class checks the build as code requirement.

    See https://slsa.dev/spec/v0.1/requirements#build-as-code.
    """

    def __init__(self) -> None:
        """Initiate the BuildAsCodeCheck instance."""
        description = (
            "The build definition and configuration executed by the build "
            "service is verifiably derived from text file definitions "
            "stored in a version control system."
        )
        depends_on: list[tuple[str, CheckResultType]] = [
            ("mcn_trusted_builder_level_three_1", CheckResultType.FAILED),
        ]
        eval_reqs = [ReqName.BUILD_AS_CODE]
        super().__init__(
            check_id="mcn_build_as_code_1",
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.PASSED,
        )

    def _has_deploy_command(self, commands: list[list[str]], build_tool: BaseBuildTool) -> str:
        """Check if the bash command is a build and deploy command."""
        # Account for Python projects having separate tools for packaging and publishing.
        deploy_tool = build_tool.publisher if build_tool.publisher else build_tool.builder
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

            check_build_commands = any(build_cmd for build_cmd in deploy_tool if build_cmd == cmd_program_name)

            # Support the use of interpreters like Python that load modules, i.e., 'python -m pip install'.
            check_module_build_commands = any(
                interpreter == cmd_program_name
                and com[1]
                and com[1] in build_tool.interpreter_flag
                and com[2]
                and com[2] in deploy_tool
                for interpreter in build_tool.interpreter
            )
            prog_name_index = 2 if check_module_build_commands else 0

            if check_build_commands or check_module_build_commands:
                # Check the arguments in the bash command for the deploy goals.
                # If there are no deploy args for this build tool, accept as deploy command.
                # TODO: Support multi-argument build keywords, issue #493.
                if not build_tool.deploy_arg:
                    logger.info("No deploy arguments required. Accept %s as deploy command.", str(com))
                    return str(com)

                for word in com[(prog_name_index + 1) :]:
                    # TODO: allow plugin versions in arguments, e.g., maven-plugin:1.6.8:deploy.
                    if word in build_tool.deploy_arg:
                        logger.info("Found deploy command %s.", str(com))
                        return str(com)
        return ""

    def _check_build_tool(
        self,
        build_tool: BaseBuildTool,
        ctx: AnalyzeContext,
        ci_services: list[CIInfo],
        justification: Justification,
        result_tables: ResultTables,
    ) -> CheckResultType:
        """Run the check for a single build tool to determine if "build as code" holds for it.

        Parameters
        ----------
        build_tool: BaseBuildTool
            The build tool to run the check for.
        ctx : AnalyzeContext
            The object containing processed data for the target repo.
        ci_services: list[CIInfo]
            List of CI services in use.
        justification: Justification
            List of justifications to add to.
        result_tables: ResultTables
            List of result tables to add to.

        Returns
        -------
        CheckResultType
            The result type of the check (e.g. PASSED).
        """
        if build_tool:
            for ci_info in ci_services:
                ci_service = ci_info["service"]
                # Checking if a CI service is discovered for this repo.
                if isinstance(ci_service, NoneCIService):
                    continue

                trusted_deploy_actions = build_tool.ci_deploy_kws["github_actions"] or []

                # Check for use of a trusted GitHub Actions workflow to publish/deploy.
                # TODO: verify that deployment is legitimate and not a test
                if trusted_deploy_actions:
                    for callee in ci_info["callgraph"].bfs():
                        workflow_name = callee.name.split("@")[0]

                        if not workflow_name or callee.node_type not in [
                            GHWorkflowType.EXTERNAL,
                            GHWorkflowType.REUSABLE,
                        ]:
                            logger.debug("Workflow %s is not relevant. Skipping...", callee.name)
                            continue
                        if workflow_name in trusted_deploy_actions:
                            trigger_link = ci_service.api_client.get_file_link(
                                ctx.component.repository.full_name,
                                ctx.component.repository.commit_sha,
                                ci_service.api_client.get_relative_path_of_workflow(
                                    os.path.basename(callee.caller_path)
                                ),
                            )
                            deploy_action_source_link = ci_service.api_client.get_file_link(
                                ctx.component.repository.full_name,
                                ctx.component.repository.commit_sha,
                                callee.caller_path,
                            )

                            html_url = ci_service.has_latest_run_passed(
                                ctx.component.repository.full_name,
                                ctx.component.repository.branch_name,
                                ctx.component.repository.commit_sha,
                                ctx.component.repository.commit_date,
                                callee.caller_path,
                            )

                            # TODO: include in the justification multiple cases of external action usage
                            justification_action: Justification = [
                                {
                                    f"The target repository uses build tool {build_tool.name}"
                                    " to deploy": deploy_action_source_link,
                                    "The build is triggered by": trigger_link,
                                },
                                f"Deploy action: {workflow_name}",
                                {"The status of the build can be seen at": html_url}
                                if html_url
                                else "However, could not find a passing workflow run.",
                            ]
                            justification.extend(justification_action)
                            if (
                                ctx.dynamic_data["is_inferred_prov"]
                                and ci_info["provenances"]
                                and isinstance(ci_info["provenances"][0], InTotoV01Payload)
                            ):
                                predicate: Any = ci_info["provenances"][0].statement["predicate"]
                                predicate["buildType"] = f"Custom {ci_service.name}"
                                predicate["builder"]["id"] = deploy_action_source_link
                                predicate["invocation"]["configSource"]["uri"] = (
                                    f"{ctx.component.repository.remote_path}"
                                    f"@refs/heads/{ctx.component.repository.branch_name}"
                                )
                                predicate["invocation"]["configSource"]["digest"][
                                    "sha1"
                                ] = ctx.component.repository.commit_sha
                                predicate["invocation"]["configSource"]["entryPoint"] = trigger_link
                                predicate["metadata"]["buildInvocationId"] = html_url
                            result_tables.append(
                                BuildAsCodeFacts(
                                    build_tool_name=build_tool.name,
                                    ci_service_name=ci_service.name,
                                    build_trigger=trigger_link,
                                    deploy_command=workflow_name,
                                    build_status_url=html_url,
                                )
                            )
                            return CheckResultType.PASSED

                for bash_cmd in ci_info["bash_commands"]:
                    deploy_cmd = self._has_deploy_command(bash_cmd["commands"], build_tool)
                    if deploy_cmd:
                        # Get the permalink and HTML hyperlink tag of the CI file that triggered the bash command.
                        trigger_link = ci_service.api_client.get_file_link(
                            ctx.component.repository.full_name,
                            ctx.component.repository.commit_sha,
                            ci_service.api_client.get_relative_path_of_workflow(os.path.basename(bash_cmd["CI_path"])),
                        )
                        # Get the permalink of the source file of the bash command.
                        bash_source_link = ci_service.api_client.get_file_link(
                            ctx.component.repository.full_name,
                            ctx.component.repository.commit_sha,
                            bash_cmd["caller_path"],
                        )

                        html_url = ci_service.has_latest_run_passed(
                            ctx.component.repository.full_name,
                            ctx.component.repository.branch_name,
                            ctx.component.repository.commit_sha,
                            ctx.component.repository.commit_date,
                            bash_cmd["CI_path"],
                        )

                        justification_cmd: Justification = [
                            {
                                f"The target repository uses build tool {build_tool.name} to deploy": bash_source_link,
                                "The build is triggered by": trigger_link,
                            },
                            f"Deploy command: {deploy_cmd}",
                            {"The status of the build can be seen at": html_url}
                            if html_url
                            else "However, could not find a passing workflow run.",
                        ]
                        justification.extend(justification_cmd)
                        if (
                            ctx.dynamic_data["is_inferred_prov"]
                            and ci_info["provenances"]
                            and isinstance(ci_info["provenances"][0], InTotoV01Payload)
                        ):
                            predicate = ci_info["provenances"][0].statement["predicate"]
                            predicate["buildType"] = f"Custom {ci_service.name}"
                            predicate["builder"]["id"] = bash_source_link
                            predicate["invocation"]["configSource"]["uri"] = (
                                f"{ctx.component.repository.remote_path}"
                                f"@refs/heads/{ctx.component.repository.branch_name}"
                            )
                            predicate["invocation"]["configSource"]["digest"][
                                "sha1"
                            ] = ctx.component.repository.commit_sha
                            predicate["invocation"]["configSource"]["entryPoint"] = trigger_link
                            predicate["buildConfig"]["jobID"] = bash_cmd["job_name"]
                            predicate["buildConfig"]["stepID"] = bash_cmd["step_name"]
                            predicate["metadata"]["buildInvocationId"] = html_url
                        result_tables.append(
                            BuildAsCodeFacts(
                                build_tool_name=build_tool.name,
                                ci_service_name=ci_service.name,
                                build_trigger=trigger_link,
                                deploy_command=deploy_cmd,
                                build_status_url=html_url,
                            )
                        )

                        return CheckResultType.PASSED

                # We currently don't parse these CI configuration files.
                # We just look for a keyword for now.
                for unparsed_ci in (Jenkins, Travis, CircleCI, GitLabCI):
                    if isinstance(ci_service, unparsed_ci):
                        if build_tool.ci_deploy_kws[ci_service.name]:
                            deploy_kw, config_name = ci_service.has_kws_in_config(
                                build_tool.ci_deploy_kws[ci_service.name], repo_path=ctx.component.repository.fs_path
                            )
                            if not config_name:
                                break
                            justification.append(
                                f"The target repository uses build tool {build_tool.name}"
                                + f" in {ci_service.name} using {deploy_kw} to deploy."
                            )

                            if (
                                ctx.dynamic_data["is_inferred_prov"]
                                and ci_info["provenances"]
                                and isinstance(ci_info["provenances"][0], InTotoV01Payload)
                            ):
                                predicate = ci_info["provenances"][0].statement["predicate"]
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
                            result_tables.append(
                                BuildAsCodeFacts(
                                    build_tool_name=build_tool.name,
                                    ci_service_name=ci_service.name,
                                    deploy_command=deploy_kw,
                                )
                            )
                            return CheckResultType.PASSED

        pass_msg = f"The target repository does not use {build_tool.name} to deploy."
        justification.append(pass_msg)
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
        # Get the build tool identified by the mcn_version_control_system_1, which we depend on.
        build_tools = ctx.dynamic_data["build_spec"]["tools"]

        if not build_tools:
            failed_msg = "The target repository does not have any build tools."
            return CheckResultData(justification=[failed_msg], result_tables=[], result_type=CheckResultType.FAILED)

        ci_services = ctx.dynamic_data["ci_services"]

        # Check if "build as code" holds for each build tool.
        overall_res = CheckResultType.FAILED

        justification: Justification = []
        result_tables: ResultTables = []
        for tool in build_tools:
            res = self._check_build_tool(tool, ctx, ci_services, justification, result_tables)

            if res == CheckResultType.PASSED:
                # The check passing is contingent on at least one passing, if
                # one passes treat whole check as passing. We do still need to
                # run the others for justifications though to report multiple
                # build tool usage.
                # TODO: When more sophisticated build tool detection is
                # implemented, consider whether this should be one fail = whole
                # check fails instead
                overall_res = CheckResultType.PASSED

        return CheckResultData(justification=justification, result_tables=result_tables, result_type=overall_res)


registry.register(BuildAsCodeCheck())
