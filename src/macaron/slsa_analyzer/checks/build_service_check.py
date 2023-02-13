# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildServiceCheck class."""

import logging
import os

from sqlalchemy import Column
from sqlalchemy.sql.sqltypes import String

from macaron.database.database_manager import ORMBase
from macaron.database.table_definitions import CheckFactsTable
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, NoneBuildTool
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.ci_service.base_ci_service import NoneCIService
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class BuildServiceCheck(BaseCheck):
    """This Check checks whether the target repo has a valid build service."""

    class ResultTable(CheckFactsTable, ORMBase):
        """Check justification table for build_service."""

        __tablename__ = "_build_service_check"
        build_tool_name = Column(String)
        ci_service_name = Column(String)
        build_trigger = Column(String)

    def __init__(self) -> None:
        """Initiate the BuildServiceCheck instance."""
        check_id = "mcn_build_service_1"
        description = "Check if the target repo has a valid build service."
        depends_on = [("mcn_build_as_code_1", CheckResultType.FAILED)]
        eval_reqs = [ReqName.BUILD_SERVICE]
        super().__init__(
            check_id=check_id,
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.PASSED,
        )

    def _has_build_command(self, commands: list[list[str]], build_tool: BaseBuildTool) -> str:
        """Check if the bash command is a build command."""
        for com in commands:
            # Check for empty or invalid commands.
            if not com or not com[0]:
                continue
            # The first argument in a bash command is the program name.
            # So first check that the program name is a supported build tool name.
            # We need to handle cases where the the first argument is a path to the program.
            cmd_program_name = os.path.basename(com[0])
            if not cmd_program_name:
                logger.debug("Found invalid program name %s.", com[0])
                continue
            if any(build_cmd for build_cmd in build_tool.builder if build_cmd == cmd_program_name):
                # Check the arguments in the bash command for the build goals.
                # If there are no build args for this build tool, accept as build command.
                if not build_tool.build_arg:
                    logger.info("No build arguments required. Accept %s as build command.", str(com))
                    return str(com)
                for word in com[1:]:
                    # TODO: allow plugin versions in arguments, e.g., maven-plugin:1.6.8:package.
                    if word in build_tool.build_arg:
                        logger.info("Found build command %s.", str(com))
                        return str(com)
        return ""

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
        build_tool = ctx.dynamic_data["build_spec"].get("tool")
        ci_services = ctx.dynamic_data["ci_services"]

        # Checking if a build tool is discovered for this repo.
        if build_tool and not isinstance(build_tool, NoneBuildTool):
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
                            ctx.repo_full_name,
                            ctx.commit_sha,
                            ci_service.api_client.get_relative_path_of_workflow(os.path.basename(bash_cmd["CI_path"])),
                        )
                        # Get the permalink and HTML hyperlink tag of the source file of the bash command.
                        bash_source_link = ci_service.api_client.get_file_link(
                            ctx.repo_full_name, ctx.commit_sha, bash_cmd["caller_path"]
                        )

                        html_url = ci_service.has_latest_run_passed(
                            ctx.repo_full_name,
                            ctx.branch_name,
                            ctx.commit_sha,
                            ctx.commit_date,
                            os.path.basename(bash_cmd["CI_path"]),
                        )

                        justification: list[str | dict[str, str]] = [
                            {
                                f"The target repository uses build tool {build_tool.name} to deploy": bash_source_link,
                                "The build is triggered by": trigger_link,
                            },
                            f"Build command: {build_cmd}",
                            {"The status of the build can be seen at": html_url}
                            if html_url
                            else "However, could not find a passing workflow run.",
                        ]
                        check_result["justification"].extend(justification)
                        check_result["result_tables"] = [
                            BuildServiceCheck.ResultTable(
                                build_tool_name=build_tool.name,
                                build_trigger=trigger_link,
                                ci_service_name=ci_service.name,
                            )
                        ]

                        if ctx.dynamic_data["is_inferred_prov"] and ci_info["provenances"]:
                            predicate = ci_info["provenances"][0]["predicate"]
                            predicate["buildType"] = f"Custom {ci_service.name}"
                            predicate["builder"]["id"] = bash_source_link
                            predicate["invocation"]["configSource"][
                                "uri"
                            ] = f"{ctx.remote_path}@refs/heads/{ctx.branch_name}"
                            predicate["invocation"]["configSource"]["digest"]["sha1"] = ctx.commit_sha
                            predicate["invocation"]["configSource"]["entryPoint"] = trigger_link
                            predicate["metadata"]["buildInvocationId"] = html_url
                        return CheckResultType.PASSED

                # We currently don't parse these CI configuration files.
                # We just look for a keyword for now.
                for unparsed_ci in (Jenkins, Travis, CircleCI, GitLabCI):
                    if isinstance(ci_service, unparsed_ci):
                        if build_tool.ci_build_kws[ci_service.name]:
                            config_name = ci_service.has_kws_in_config(
                                build_tool.ci_build_kws[ci_service.name], repo_path=ctx.repo_path
                            )
                            if not config_name:
                                break

                            check_result["justification"].append(
                                f"The target repository uses "
                                f"build tool {build_tool.name} in {ci_service.name} to "
                                f"build."
                            )
                            check_result["result_tables"] = [
                                BuildServiceCheck.ResultTable(
                                    build_tool_name=build_tool.name,
                                    ci_service_name=ci_service.name,
                                )
                            ]

                            if ctx.dynamic_data["is_inferred_prov"] and ci_info["provenances"]:
                                predicate = ci_info["provenances"][0]["predicate"]
                                predicate["buildType"] = f"Custom {ci_service.name}"
                                predicate["builder"]["id"] = config_name
                                predicate["invocation"]["configSource"][
                                    "uri"
                                ] = f"{ctx.remote_path}@refs/heads/{ctx.branch_name}"
                                predicate["invocation"]["configSource"]["digest"]["sha1"] = ctx.commit_sha
                                predicate["invocation"]["configSource"]["entryPoint"] = config_name
                            return CheckResultType.PASSED

        fail_msg = "The target repository does not have a build service."
        check_result["justification"].append(fail_msg)
        return CheckResultType.FAILED


registry.register(BuildServiceCheck())
