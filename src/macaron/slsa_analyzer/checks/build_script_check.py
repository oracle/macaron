# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildScriptCheck class."""

import logging

from sqlalchemy import Column
from sqlalchemy.sql.sqltypes import String

from macaron.database.database_manager import ORMBase
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.base_build_tool import NoneBuildTool
from macaron.slsa_analyzer.checks.base_check import BaseCheck, CheckFactsTable
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class BuildScriptCheck(BaseCheck):
    """This Check checks whether the target repo has a valid build script."""

    class ResultTable(CheckFactsTable, ORMBase):
        """Check result table for build_script."""

        __tablename__ = "_build_script_check"
        build_tool_name = Column(String)

    def __init__(self) -> None:
        """Initiate the BuildScriptCheck instance."""
        check_id = "mcn_build_script_1"
        description = "Check if the target repo has a valid build script."
        depends_on = [("mcn_build_service_1", CheckResultType.FAILED)]
        eval_reqs = [ReqName.SCRIPTED_BUILD]
        super().__init__(
            check_id=check_id,
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
        build_tool = ctx.dynamic_data["build_spec"].get("tool")

        # Check if a build tool is discovered for this repo.
        # TODO: look for build commands in the bash scripts. Currently
        # we parse bash scripts that are reachable through CI only.
        if build_tool and not isinstance(build_tool, NoneBuildTool):
            pass_msg = f"The target repository uses build tool {build_tool.name}."
            check_result["justification"].append(pass_msg)
            check_result["result_tables"] = [BuildScriptCheck.ResultTable(build_tool_name=build_tool.name)]
            return CheckResultType.PASSED

        failed_msg = "The target repository does not have a build tool."
        check_result["justification"].append(failed_msg)
        return CheckResultType.FAILED


registry.register(BuildScriptCheck())
