# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildScriptCheck class."""

import logging

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
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

    __mapper_args__ = {
        "polymorphic_identity": "_build_script_check",
    }


class BuildScriptCheck(BaseCheck):
    """This Check checks whether the target repo has a valid build script."""

    def __init__(self) -> None:
        """Initiate the BuildScriptCheck instance."""
        check_id = "mcn_build_script_1"
        description = "Check if the target repo has a valid build script."
        depends_on: list[tuple[str, CheckResultType]] = [("mcn_build_service_1", CheckResultType.FAILED)]
        eval_reqs = [ReqName.SCRIPTED_BUILD]
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
        build_tools = ctx.dynamic_data["build_spec"]["tools"]

        if not build_tools:
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        # Check if any build tools are discovered for this repo.
        # TODO: look for build commands in the bash scripts. Currently
        #       we parse bash scripts that are reachable through CI only.
        result_tables: list[CheckFacts] = []
        for tool in build_tools:
            result_tables.append(BuildScriptFacts(build_tool_name=tool.name, confidence=Confidence.HIGH))

        return CheckResultData(result_tables=result_tables, result_type=CheckResultType.PASSED)


registry.register(BuildScriptCheck())
