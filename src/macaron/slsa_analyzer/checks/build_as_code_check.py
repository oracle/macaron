# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildAsCodeCheck class."""

import logging

from problog import get_evaluatable
from problog.program import PrologString, Term
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Float, String

from macaron.database.database_manager import ORMBase
from macaron.database.table_definitions import CheckFactsTable
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.base_build_tool import NoneBuildTool
from macaron.slsa_analyzer.checks import build_as_code_subchecks
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.build_as_code_subchecks import BuildAsCodeSubchecks, DeploySubcheckResults
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.ci_service.base_ci_service import NoneCIService
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class BuildAsCodeTable(CheckFactsTable, ORMBase):
    """Check justification table for build_as_code."""

    __tablename__ = "_build_as_code_check"
    build_tool_name: Mapped[str] = mapped_column(String, nullable=True)
    ci_service_name: Mapped[str] = mapped_column(String, nullable=True)
    build_trigger: Mapped[str] = mapped_column(String, nullable=True)
    deploy_command: Mapped[str] = mapped_column(String, nullable=True)
    build_status_url: Mapped[str] = mapped_column(String, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=True)


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
        depends_on = [
            ("mcn_trusted_builder_level_three_1", CheckResultType.FAILED),
        ]
        eval_reqs = [ReqName.BUILD_AS_CODE]
        self.confidence_score_threshold = 0.3

        super().__init__(
            check_id="mcn_build_as_code_1",
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.PASSED,
        )

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
        # Get the build tool identified by the mcn_version_control_system_1, which we depend on.
        build_tool = ctx.dynamic_data["build_spec"].get("tool")
        ci_services = ctx.dynamic_data["ci_services"]

        # Checking if a build tool is discovered for this repo.
        if build_tool and not isinstance(build_tool, NoneBuildTool):
            for ci_info in ci_services:
                confidence_score = 0.0
                ci_service = ci_info["service"]
                # Checking if a CI service is discovered for this repo.
                if isinstance(ci_service, NoneCIService):
                    continue

                # Initialize the BuildAsCodeSubchecks object with the AnalyzeContext.
                build_as_code_subchecks.build_as_code_subcheck_results = BuildAsCodeSubchecks(ctx=ctx, ci_info=ci_info)

                # ProbLog rules to be evaluated.
                prolog_string = PrologString(
                    """
                    :- use_module('src/macaron/slsa_analyzer/checks/problog_predicates.py').

                    A :: ci_parsed :- ci_parsed_check(A).
                    B :: deploy_action :- deploy_action_check(B).
                    C :: deploy_command :- deploy_command_check(C).
                    D :: deploy_kws :- deploy_kws_check(D).

                    0.80 :: deploy_action_certainty :- deploy_action.
                    0.15 :: deploy_action_certainty :- deploy_action, ci_parsed.

                    0.70 :: deploy_command_certainty :- deploy_command.
                    0.15 :: deploy_command_certainty :- deploy_command, ci_parsed.

                    0.60 :: deploy_kws_certainty :- deploy_kws.

                    build_as_code_check :- deploy_action_certainty; deploy_command_certainty; deploy_kws_certainty.

                    query(deploy_command_certainty).
                    query(deploy_action_certainty).
                    query(deploy_kws_certainty).
                    query(build_as_code_check).
                    """
                )

                # Convert the result dictionary from Term:float to str:float
                term_result: dict[Term, float] = get_evaluatable().create_from(prolog_string).evaluate()
                result: dict[str, float] = {str(key): value for key, value in term_result.items()}
                deploy_methods = {
                    "deploy_command": result["deploy_command_certainty"],
                    "deploy_action": result["deploy_action_certainty"],
                    "deploy_kws": result["deploy_kws_certainty"],
                }
                deploy_methods_valid = {key: value for key, value in deploy_methods.items() if value != 0}
                confidence_score = result["build_as_code_check"]
                check_result["confidence_score"] = confidence_score

                if deploy_methods_valid.values():
                    # Determine the deployment method with the highest certainty score.
                    highest_certainty = max(deploy_methods_valid, key=deploy_methods_valid.__getitem__)
                    deploy_method = build_as_code_subchecks.build_as_code_subcheck_results.get_subcheck_results(
                        highest_certainty
                    )

                    if isinstance(deploy_method, DeploySubcheckResults):
                        if ctx.dynamic_data["is_inferred_prov"] and ci_info["provenances"]:
                            predicate = ci_info["provenances"][0]["predicate"]
                            predicate["buildType"] = f"Custom {ci_service.name}"
                            predicate["invocation"]["configSource"][
                                "uri"
                            ] = f"{ctx.remote_path}@refs/heads/{ctx.branch_name}"
                            predicate["invocation"]["configSource"]["digest"]["sha1"] = ctx.commit_sha

                            predicate["metadata"]["buildInvocationId"] = deploy_method.html_url
                            predicate["builder"]["id"] = deploy_method.source_link
                            predicate["invocation"]["configSource"]["entryPoint"] = deploy_method.trigger_link

                            if highest_certainty == "deploy_kws":
                                predicate["builder"]["id"] = deploy_method.config_name
                                predicate["invocation"]["configSource"]["entryPoint"] = deploy_method.config_name

                        check_result["result_tables"] = [
                            BuildAsCodeTable(
                                build_tool_name=build_tool.name,
                                ci_service_name=ci_service.name,
                                build_trigger=deploy_method.trigger_link,
                                deploy_command=deploy_method.deploy_cmd,
                                build_status_url=deploy_method.html_url,
                                confidence_score=confidence_score,
                            )
                        ]

                # TODO: compile all justifications
                # check_result["justification"].append()

                # TODO: Investigate using proofs

                # Check whether the confidence score is greater than the minimum threshold for this check.
                if confidence_score >= self.confidence_score_threshold:
                    logger.info("The certainty of this check passing is: %s", confidence_score)
                    return CheckResultType.PASSED

            pass_msg = f"The target repository does not use {build_tool.name} to deploy."
            check_result["justification"].append(pass_msg)
            check_result["result_tables"] = [BuildAsCodeTable(build_tool_name=build_tool.name)]
            return CheckResultType.FAILED

        check_result["result_tables"] = [BuildAsCodeTable()]
        failed_msg = "The target repository does not have a build tool."
        check_result["justification"].append(failed_msg)
        return CheckResultType.FAILED


registry.register(BuildAsCodeCheck())
