# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildAsCodeCheck class."""

import logging
import os

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.code_analyzer.dataflow_analysis.analysis import get_build_tool_commands, get_containing_github_job
from macaron.code_analyzer.dataflow_analysis.core import traverse_bfs
from macaron.code_analyzer.dataflow_analysis.github import (
    GitHubActionsActionStepNode,
    GitHubActionsReusableWorkflowCallNode,
    GitHubActionsRunStepNode,
)
from macaron.database.table_definitions import CheckFacts
from macaron.errors import CallGraphError, ProvenanceError
from macaron.provenance.provenance_extractor import ProvenancePredicate
from macaron.slsa_analyzer.analyze_context import AnalyzeContext, store_inferred_build_info_results
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService, NoneCIService
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class BuildAsCodeFacts(CheckFacts):
    """The ORM mapping for justifications in build_as_code check."""

    __tablename__ = "_build_as_code_check"

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

    #: The URL that provides information about the language distributions and versions.
    language_url: Mapped[str | None] = mapped_column(
        String, nullable=True, info={"justification": JustificationType.HREF}
    )

    #: The command used to deploy.
    deploy_command: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.TEXT})

    __mapper_args__ = {
        "polymorphic_identity": "_build_as_code_check",
    }


class BuildAsCodeCheck(BaseCheck):
    """This check analyzes the CI configurations to determine if the software component is published automatically.

    As a requirement of this check, the software component should be published using a hosted build service.
    """

    def __init__(self) -> None:
        """Initiate the BuildAsCodeCheck instance."""
        description = (
            "Check if the build definition and configuration executed by the build "
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

        # If a provenance is found, obtain the workflow that has triggered the artifact release.
        prov_workflow = None
        prov_payload = None
        if ctx.dynamic_data["provenance_info"]:
            prov_payload = ctx.dynamic_data["provenance_info"].provenance_payload
        if not ctx.dynamic_data["is_inferred_prov"] and prov_payload:
            try:
                build_def = ProvenancePredicate.find_build_def(prov_payload.statement)
            except ProvenanceError as error:
                logger.error(error)
                return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)
            prov_workflow, _ = build_def.get_build_invocation(prov_payload.statement)

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

                callgraph = ci_info["callgraph"]

                trusted_deploy_actions = tool.ci_deploy_kws["github_actions"] or []

                # Check for use of a trusted GitHub Actions workflow to publish/deploy.
                # TODO: verify that deployment is legitimate and not a test
                if trusted_deploy_actions:
                    for root in ci_info["callgraph"].root_nodes:
                        for callee in traverse_bfs(root):
                            if isinstance(callee, (GitHubActionsReusableWorkflowCallNode, GitHubActionsActionStepNode)):
                                workflow_name = callee.uses_name

                                if workflow_name in trusted_deploy_actions:
                                    job_id = None
                                    step_id = None
                                    step_name = None
                                    caller_path = ""
                                    job = (
                                        get_containing_github_job(callee, callgraph.parents)
                                        if isinstance(callee, GitHubActionsActionStepNode)
                                        else callee
                                    )

                                    if not job:
                                        continue

                                    job_id = job.job_id
                                    caller_path = job.context.ref.workflow_context.ref.source_filepath

                                    # Only third-party Actions can be called from a step.
                                    # Reusable workflows have to be directly called from the job.
                                    # See https://docs.github.com/en/actions/sharing-automations/ \
                                    # reusing-workflows#calling-a-reusable-workflow
                                    if isinstance(callee, GitHubActionsActionStepNode):
                                        callee_node_type = "external"
                                        if "id" in callee.definition:
                                            step_id = callee.definition["id"]
                                        if "name" in callee.definition:
                                            step_name = callee.definition["name"]
                                    else:
                                        callee_node_type = "reusable"

                                    trigger_link = ci_service.api_client.get_file_link(
                                        ctx.component.repository.full_name,
                                        ctx.component.repository.commit_sha,
                                        file_path=(
                                            ci_service.api_client.get_relative_path_of_workflow(
                                                os.path.basename(caller_path)
                                            )
                                            if caller_path
                                            else ""
                                        ),
                                    )

                                    trusted_workflow_confidence = tool.infer_confidence_deploy_workflow(
                                        ci_path=caller_path, provenance_workflow=prov_workflow
                                    )
                                    # Store or update the inferred build information if the confidence
                                    # for the current check fact is bigger than the maximum score.
                                    if (
                                        not result_tables
                                        or trusted_workflow_confidence
                                        > max(result_tables, key=lambda item: item.confidence).confidence
                                    ):
                                        store_inferred_build_info_results(
                                            ctx=ctx,
                                            ci_info=ci_info,
                                            ci_service=ci_service,
                                            trigger_link=trigger_link,
                                            job_id=job_id,
                                            step_id=step_id,
                                            step_name=step_name,
                                            callee_node_type=callee_node_type,
                                        )
                                    result_tables.append(
                                        BuildAsCodeFacts(
                                            build_tool_name=tool.name,
                                            ci_service_name=ci_service.name,
                                            build_trigger=trigger_link,
                                            language=tool.language.value,
                                            deploy_command=workflow_name,
                                            confidence=trusted_workflow_confidence,
                                        )
                                    )
                                    overall_res = CheckResultType.PASSED

                try:
                    for build_command in get_build_tool_commands(nodes=callgraph, build_tool=tool):
                        # Yes or no with a confidence score.
                        result, confidence = tool.is_deploy_command(
                            build_command,
                            ci_service.get_third_party_configurations(),
                            provenance_workflow=prov_workflow,
                        )
                        if result:
                            trigger_link = ci_service.api_client.get_file_link(
                                ctx.component.repository.full_name,
                                ctx.component.repository.commit_sha,
                                ci_service.api_client.get_relative_path_of_workflow(
                                    os.path.basename(build_command["ci_path"])
                                ),
                            )
                            # Store or update the inferred build information if the confidence
                            # for the current check fact is bigger than the maximum score.
                            if (
                                not result_tables
                                or confidence > max(result_tables, key=lambda item: item.confidence).confidence
                            ):
                                job_id = None
                                step_id = None
                                step_name = None
                                step_node = build_command["step_node"]
                                if step_node:
                                    job_node = get_containing_github_job(step_node, callgraph.parents)
                                    if job_node is not None:
                                        job_id = job_node.job_id

                                    if isinstance(step_node, GitHubActionsRunStepNode):
                                        step_id = step_node.definition.get("id")
                                        step_name = step_node.definition.get("name")

                                store_inferred_build_info_results(
                                    ctx=ctx,
                                    ci_info=ci_info,
                                    ci_service=ci_service,
                                    trigger_link=trigger_link,
                                    job_id=job_id,
                                    step_id=step_id,
                                    step_name=step_name,
                                )
                            result_tables.append(
                                BuildAsCodeFacts(
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
                                    deploy_command=tool.serialize_to_json(build_command["command"]),
                                    confidence=confidence,
                                )
                            )
                            overall_res = CheckResultType.PASSED
                except CallGraphError as error:
                    logger.debug(error)

                # We currently don't parse these CI configuration files.
                # We just look for a keyword for now.
                for unparsed_ci in (Travis, CircleCI, GitLabCI):
                    if isinstance(ci_service, unparsed_ci):
                        if tool.ci_deploy_kws[ci_service.name]:
                            deploy_kw, config_name = ci_service.has_kws_in_config(
                                tool.ci_deploy_kws[ci_service.name],
                                build_tool_name=tool.name,
                                repo_path=ctx.component.repository.fs_path,
                            )
                            if not config_name:
                                break

                            store_inferred_build_info_results(
                                ctx=ctx, ci_info=ci_info, ci_service=ci_service, trigger_link=config_name
                            )
                            result_tables.append(
                                BuildAsCodeFacts(
                                    build_tool_name=tool.name,
                                    language=tool.language.value,
                                    ci_service_name=ci_service.name,
                                    deploy_command=deploy_kw,
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


registry.register(BuildAsCodeCheck())
