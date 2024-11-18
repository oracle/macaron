# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the TrustedBuilderL3Check class."""

import logging
import os

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.config.defaults import defaults
from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext, store_inferred_build_info_results
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.ci_service.github_actions.analyzer import (
    GitHubJobNode,
    GitHubWorkflowNode,
    GitHubWorkflowType,
)
from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class TrustedBuilderFacts(CheckFacts):
    """The ORM mapping for justifications in trusted_builder."""

    __tablename__ = "_trusted_builder_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The name of the tool used to build.
    build_tool_name: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The CI service name used to build.
    ci_service_name: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The entrypoint script that triggers the build.
    build_trigger: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

    __mapper_args__ = {
        "polymorphic_identity": "_trusted_builder_check",
    }


class TrustedBuilderL3Check(BaseCheck):
    """This Check checks whether the target repo uses level 3 builders."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_trusted_builder_level_three_1"
        description = "Check whether the target uses a trusted SLSA level 3 builder."
        depends_on: list[tuple[str, CheckResultType]] = [("mcn_version_control_system_1", CheckResultType.PASSED)]
        # See https://github.com/slsa-framework/slsa-github-generator/
        # blob/main/SPECIFICATIONS.md#build-level-provenance.

        # See https://github.com/slsa-framework/slsa/issues/465:
        # From #464: SLSA 3 only guarantees identification of the top-level build configuration
        # used to initiate the build. It makes no guarantee about what actually happened during
        # the build, particularly the "source" that was built. For example, if GitHub Actions
        # attests to building octocat/Spoon-Knife, all it's saying is that the workflow was defined
        # in that file. There is no guarantee that this workflow actually checked out and built
        # the same repo. The main reason for this definition is because there is no widely accepted
        # technical definition of "source" (#129) and therefore no corresponding technical control,
        # whereas we can cleanly define top-level build configuration and build a control around it.

        eval_reqs = [
            ReqName.HERMETIC,
            ReqName.ISOLATED,
            ReqName.PARAMETERLESS,
            ReqName.EPHEMERAL_ENVIRONMENT,
        ]
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
        # TODO: During verification, we need to fetch the workflow and verify that it's not
        # using self-hosted runners, custom containers or services, etc.
        found_builder = False
        ci_services = ctx.dynamic_data["ci_services"]
        result_values = []
        result_tables: list[CheckFacts] = []

        for ci_info in ci_services:
            ci_service = ci_info["service"]
            # We only support GitHub Actions for now.
            if not isinstance(ci_service, GitHubActions):
                continue

            trusted_builders = defaults.get_list("ci.github_actions", "trusted_builders", fallback=[])

            # Look for trusted builders called as GitHub Actions.
            for callee in ci_info["callgraph"].bfs():
                if isinstance(callee, GitHubWorkflowNode):
                    workflow_name = callee.name.split("@")[0]

                    # Check if the action is called as a third-party or reusable workflow.
                    if not workflow_name or callee.node_type not in [
                        GitHubWorkflowType.EXTERNAL,
                        GitHubWorkflowType.REUSABLE,
                    ]:
                        logger.debug("Workflow %s is not relevant. Skipping...", callee.name)
                        continue
                    if workflow_name in trusted_builders:
                        caller_path = callee.caller.source_path if isinstance(callee.caller, GitHubJobNode) else ""
                        caller_link = ci_service.api_client.get_file_link(
                            ctx.component.repository.full_name,
                            ctx.component.repository.commit_sha,
                            ci_service.api_client.get_relative_path_of_workflow(os.path.basename(caller_path)),
                        )

                        store_inferred_build_info_results(
                            ctx=ctx, ci_info=ci_info, ci_service=ci_service, trigger_link=caller_link
                        )

                        found_builder = True
                        result_values.append(
                            {
                                "build_tool_name": callee.name,
                                "build_trigger": caller_link,
                                "ci_service_name": ci_service.name,
                            }
                        )

        result_tables = [TrustedBuilderFacts(**result, confidence=Confidence.HIGH) for result in result_values]

        if found_builder:
            return CheckResultData(result_tables=result_tables, result_type=CheckResultType.PASSED)

        return CheckResultData(
            result_tables=result_tables,
            result_type=CheckResultType.FAILED,
        )


registry.register(TrustedBuilderL3Check())
