# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the implementation of the VCS check."""


from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck, CheckResultType
from macaron.slsa_analyzer.checks.check_result import CheckResult
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName


class VCSCheck(BaseCheck):
    """This Check checks whether the target repo uses a version control system."""

    def __init__(self) -> None:
        check_id = "mcn_version_control_system_1"
        description = "Check whether the target repo uses a version control system."
        depends_on: list[tuple[str, CheckResultType]] = []
        eval_reqs = [ReqName.VCS]
        super().__init__(check_id=check_id, description=description, depends_on=depends_on, eval_reqs=eval_reqs)

    def run_check(self, ctx: AnalyzeContext, check_result: CheckResult) -> CheckResultType:
        # TODO: refactor and use the git_service and its API client to create
        # the hyperlink tag to allow validation.
        if not ctx.git_obj:
            check_result["justification"].append({"This is not a Git repository": ctx.remote_path})
            return CheckResultType.FAILED

        check_result["justification"].append({"This is a Git repository": ctx.remote_path})
        return CheckResultType.PASSED


registry.register(VCSCheck())
