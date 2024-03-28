# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BaseCheck class to be inherited by other concrete Checks."""

import logging
from abc import abstractmethod

from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.check_result import (
    CheckInfo,
    CheckResult,
    CheckResultData,
    CheckResultType,
    SkippedInfo,
    get_result_as_bool,
)
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class BaseCheck:
    """This abstract class is used to implement Checks in Macaron."""

    def __init__(
        self,
        check_id: str = "",
        description: str = "",
        depends_on: list[tuple[str, CheckResultType]] | None = None,
        eval_reqs: list[ReqName] | None = None,
        result_on_skip: CheckResultType = CheckResultType.SKIPPED,
    ) -> None:
        """Initialize instance.

        Parameters
        ----------
        check_id : str
            The id of the check.
        description : str
            The description of the check.
        depends_on : list[tuple[str, CheckResultType]] | None
            The list of parent checks that this check depends on.
            Each member of the list is a tuple of the parent's id and the status
            of that parent check.
        eval_reqs : list[ReqName] | None
            The list of SLSA requirements that this check addresses.
        result_on_skip : CheckResultType
            The status for this check when it's skipped based on another check's result.
        """
        self._check_info = CheckInfo(
            check_id=check_id, check_description=description, eval_reqs=eval_reqs if eval_reqs else []
        )

        if not depends_on:
            self._depends_on = []
        else:
            self._depends_on = depends_on

        self._result_on_skip = result_on_skip

    @property
    def check_info(self) -> CheckInfo:
        """Get the information identifying/describing this check."""
        return self._check_info

    @property
    def depends_on(self) -> list[tuple[str, CheckResultType]]:
        """Get the list of parent checks that this check depends on.

        Each member of the list is a tuple of the parent's id and the status of that parent check.
        """
        return self._depends_on

    @property
    def result_on_skip(self) -> CheckResultType:
        """Get the status for this check when it's skipped based on another check's result."""
        return self._result_on_skip

    def run(self, target: AnalyzeContext, skipped_info: SkippedInfo | None = None) -> CheckResult:
        """Run the check and return the results.

        Parameters
        ----------
        target : AnalyzeContext
            The object containing processed data for the target repo.
        skipped_info : SkippedInfo | None
            Determine whether the check is skipped.

        Returns
        -------
        CheckResult
            The result of the check.
        """
        logger.info("----------------------------------")
        logger.info("BEGIN CHECK: %s", self.check_info.check_id)
        logger.info("----------------------------------")

        check_result_data: CheckResultData

        if skipped_info:
            check_result_data = CheckResultData(result_tables=[], result_type=self.result_on_skip)
            logger.debug(
                "Check %s is skipped on target %s, comment: %s",
                self.check_info.check_id,
                target.component.purl,
                skipped_info["suppress_comment"],
            )
        else:
            check_result_data = self.run_check(target)
            logger.info(
                "Check %s run %s on target %s.",
                self.check_info.check_id,
                check_result_data.result_type.value,
                target.component.purl,
            )
            logger.debug("Check result: %s", check_result_data.justification_report)

        # This justification string will be stored in the feedback column of `SLSARequirement` table.
        # TODO: Storing the justification as feedback in the `SLSARequirement` table seems redundant and might need
        # refactoring.
        justification_str = ""
        for _, ele in check_result_data.justification_report:
            justification_str += f"{str(ele)}. "

        target.bulk_update_req_status(
            self.check_info.eval_reqs,
            get_result_as_bool(check_result_data.result_type),
            justification_str,
        )

        return CheckResult(check=self.check_info, result=check_result_data)

    @abstractmethod
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
        raise NotImplementedError
