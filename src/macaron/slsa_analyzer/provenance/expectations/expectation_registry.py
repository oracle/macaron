# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The provenance expectation module manages expectations that will be provided to checks."""

import logging
import os

from macaron.database.table_definitions import CUEExpectation
from macaron.slsa_analyzer.provenance.expectations.expectation import Expectation

logger: logging.Logger = logging.getLogger(__name__)


class ExpectationRegistry:
    """
    The expectation registry class stores expectations and their results.

    Parameters
    ----------
    macaron_path: str
        The path to the macaron module
    expectation_paths: list[str]
        The list of expectation file paths. ``all((os.isfile(path) for path in expectation_paths))`` must be True.
    """

    expectations: dict[str, Expectation]
    evaluated: bool

    def __init__(self, expectation_paths: list[str]) -> None:
        self.expectations: dict[str, Expectation] = {}
        self.evaluated = False

        for expectation_path in expectation_paths:
            _, ext = os.path.splitext(expectation_path)
            if ext in (".cue",):
                expectation = CUEExpectation.make_expectation(expectation_path)
                if expectation and expectation.target:
                    self.expectations[expectation.target] = expectation
                    logger.info("Found target %s for expectation %s.", expectation.target, expectation_path)
                else:
                    logger.error("Unable to find target for expectation %s.", expectation_path)
            else:
                logger.error("Unsupported expectation format: %s", expectation_path)

    def get_expectation_for_target(self, repo_complete_name: str) -> Expectation | None:
        """
        Get the expectation that applies to a repository.

        Parameters
        ----------
        repo_complete_name: str
            The complete name of the repository, formatted "git_host/organization/repo-name"

        Returns
        -------
        Expectation | None
            An expectation if one is found, otherwise None.
        """
        if repo_complete_name in self.expectations:
            return self.expectations[repo_complete_name]
        if "any" in self.expectations:
            return self.expectations["any"]
        return None
