# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BaseCheck class to be inherited by other concrete Checks."""

import logging
from abc import abstractmethod
from typing import Optional

from sqlalchemy import Column, ForeignKey
from sqlalchemy.orm import declarative_mixin, declared_attr
from sqlalchemy.sql.sqltypes import Boolean, Integer, String

from macaron.database.database_manager import ORMBase
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType, SkippedInfo, get_result_as_bool
from macaron.slsa_analyzer.slsa_req import ReqName, get_requirements_dict

logger: logging.Logger = logging.getLogger(__name__)


class BaseCheck:
    """This abstract class is used to implement Checks in Macaron."""

    # The dictionary that contains the data of all SLSA requirements.
    SLSA_REQ_DATA = get_requirements_dict()

    def __init__(
        self,
        check_id: str = "",
        description: str = "",
        depends_on: Optional[list[tuple[str, CheckResultType]]] = None,
        eval_reqs: Optional[list[ReqName]] = None,
        result_on_skip: CheckResultType = CheckResultType.SKIPPED,
    ) -> None:
        """Initialize instance.

        Parameters
        ----------
        check_id : str
            The id of the check.
        description : str
            The description of the check.
        depends_on : Optional[list[tuple(str, CheckResultType)]]
            The list of parent checks that this check depends on.
            Each member of the list is a tuple of the parent's id and the status
            of that parent check.
        eval_reqs : Optional[list[ReqName]]
            The list of SLSA requirements that this check addresses.
        result_on_skip : CheckResultType
            The status for this check when it's skipped based on another check's result.
        """
        self.check_id = check_id
        self.description = description

        if not depends_on:
            self.depends_on = []
        else:
            self.depends_on = depends_on

        if not eval_reqs:
            self.eval_reqs = []
        else:
            self.eval_reqs = eval_reqs

        self.result_on_skip = result_on_skip

    def run(self, target: AnalyzeContext, skipped_info: Optional[SkippedInfo] = None) -> CheckResult:
        """Run the check and return the results.

        Parameters
        ----------
        target : AnalyzeContext
            The object containing processed data for the target repo.
        skipped_info : Optional[SkippedInfo]
            Determine whether the check is skipped.

        Returns
        -------
        CheckResult
            The result of the check.
        """
        logger.info("----------------------------------")
        logger.info("BEGIN CHECK: %s", self.check_id)
        logger.info("----------------------------------")

        check_result = CheckResult(
            check_id=self.check_id,
            check_description=self.description,
            slsa_requirements=[str(self.SLSA_REQ_DATA.get(req)) for req in self.eval_reqs],
            justification=[],
            result_type=CheckResultType.SKIPPED,
            result_tables=[],
        )

        if skipped_info:
            check_result["result_type"] = self.result_on_skip
            check_result["justification"].append(skipped_info["suppress_comment"])
            logger.info(
                "Check %s is skipped on target %s, comment: %s",
                self.check_id,
                target.repo_full_name,
                skipped_info["suppress_comment"],
            )
        else:
            check_result["result_type"] = self.run_check(target, check_result)
            logger.info(
                "Check %s run %s on target %s, result: %s",
                self.check_id,
                check_result["result_type"].value,
                target.repo_full_name,
                check_result["justification"],
            )

        justification_str = ""
        for ele in check_result["justification"]:
            if isinstance(ele, dict):
                for key, val in ele.items():
                    justification_str += f"{key}: {val}. "
            justification_str += f"{str(ele)}. "

        target.bulk_update_req_status(
            self.eval_reqs,
            get_result_as_bool(check_result["result_type"]),
            justification_str,
        )

        return check_result

    @abstractmethod
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
        raise NotImplementedError


class CheckResultTable(ORMBase):
    """Table to store the result of a check, is automatically added for each check."""

    __tablename__ = "_check_result"
    id = Column(Integer, primary_key=True, autoincrement=True)  # noqa: A003 # pylint: disable=invalid-name
    check_id = Column(String, nullable=False)
    repository = Column(Integer, ForeignKey("_repository.id"), nullable=False)
    passed = Column(Boolean, nullable=False)
    skipped = Column(Boolean, nullable=False)


@declarative_mixin
class CheckFactsTable:
    """
    Declarative mixin for check results.

    All tables for check results must inherit this class, these fields are automatically filled in by the analyzer.
    """

    # pylint: disable=no-member

    @declared_attr  # type: ignore
    def id(self) -> Column:  # noqa: A003 # pylint: disable=invalid-name
        """Check result id."""
        return Column(Integer, primary_key=True, autoincrement=True)

    @declared_attr  # type: ignore
    def check_result(self) -> Column:
        """Store the id of the repository to which the analysis pertains."""
        return Column(Integer, ForeignKey("_check_result.id"), nullable=False)

    @declared_attr  # type: ignore
    def repository(self) -> Column:
        """Store the id of the repository to which the analysis pertains."""
        return Column(Integer, ForeignKey("_repository.id"), nullable=False)
