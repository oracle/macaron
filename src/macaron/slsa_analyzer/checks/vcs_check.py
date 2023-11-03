# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the implementation of the VCS check."""


from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck, CheckResultType
from macaron.slsa_analyzer.checks.check_result import CheckResultData
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName


class VCSCheck(BaseCheck):
    """This Check checks whether the target repo uses a version control system."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_version_control_system_1"
        description = "Check whether the target repo uses a version control system."
        depends_on: list[tuple[str, CheckResultType]] = []
        eval_reqs = [ReqName.VCS]
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
        # TODO: refactor and use the git_service and its API client to create
        # the hyperlink tag to allow validation.
        if not ctx.component.repository:
            failed_msg = {"This is not a Git repository": ctx.component.purl}
            return CheckResultData(justification=[failed_msg], result_tables=[], result_type=CheckResultType.FAILED)

        passed_msg = {"This is a Git repository": ctx.component.repository.remote_path}
        return CheckResultData(justification=[passed_msg], result_tables=[], result_type=CheckResultType.PASSED)


registry.register(VCSCheck())
