# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the class Runner for executing checks."""


import logging
from typing import Any

from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, SkippedInfo

logger: logging.Logger = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class Runner:
    """The Runner runs a Check in its own thread and returns the Check results.

    Parameters
    ----------
    register
        The Registry that initialized this Runner.
    i : str
        The id of this Runner instance
    """

    # We use Any to prevent circular dependency
    def __init__(self, registry: Any, i: int) -> None:
        self.registry = registry
        self.runner_id = i

    def run(
        self,
        target: AnalyzeContext,
        check: BaseCheck,
        skipped_checks: list[SkippedInfo],
    ) -> CheckResult:
        """Run the check assigned by the Registry.

        After executing the Check or terminating early due to an exception, it puts
        itself back into the queue to signify Registry that it is available again for more tasks.

        Parameters
        ----------
        target : AnalyzeContext
            The object containing processed data for the target repo.
        check : BaseCheck
            The check instance to run.
        skipped_checks : list[SkippedInfo]
            The list of skipped checks information.
        """
        # TODO: Handle exceptions and time out to
        # prevent the runner to keep running indefinitely.
        logger.debug("Runner %s running check %s", self.runner_id, check.check_id)

        skip_info = None
        if skipped_checks:
            if check.check_id in [skip["id"] for skip in skipped_checks]:
                # Get the skip info from the list.
                skip_info = [skip for skip in skipped_checks if skip["id"] == check.check_id][0]

        check_result = check.run(target, skip_info)

        logger.debug("Runner %s finished check %s.", self.runner_id, check.check_id)
        self.registry.runner_queue.put(self)

        return check_result
