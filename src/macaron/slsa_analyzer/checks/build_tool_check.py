# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the implementation of the build tool detection check."""


import logging

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck, CheckResultType
from macaron.slsa_analyzer.checks.check_result import CheckResultData, Confidence, JustificationType
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class BuildToolFacts(CheckFacts):
    """The ORM mapping for the facts collected by the build tool check."""

    __tablename__ = "_build_tool_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The build tool name.
    build_tool_name: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The language of the artifact built by build tool.
    language: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    __mapper_args__ = {
        "polymorphic_identity": "_build_tool_check",
    }


class BuildToolCheck(BaseCheck):
    """This check detects the build tool used in the source code repository to build the software component."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_build_tool_1"
        description = "Detect the build tool used in the source code repository to build the software component."
        depends_on: list[tuple[str, CheckResultType]] = [("mcn_version_control_system_1", CheckResultType.PASSED)]
        eval_reqs = [ReqName.SCRIPTED_BUILD]
        super().__init__(check_id=check_id, description=description, depends_on=depends_on, eval_reqs=eval_reqs)

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
        if not ctx.component.repository:
            logger.info("Unable to find a Git repository for %s", ctx.component.purl)
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        build_tools = ctx.dynamic_data["build_spec"]["tools"]
        if not build_tools:
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        result_tables: list[CheckFacts] = []
        for tool in build_tools:
            result_tables.append(
                BuildToolFacts(build_tool_name=tool.name, language=tool.language.value, confidence=Confidence.HIGH)
            )

        return CheckResultData(
            result_tables=result_tables,
            result_type=CheckResultType.PASSED,
        )


registry.register(BuildToolCheck())
