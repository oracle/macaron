# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements CUE expectations."""
import hashlib
import logging
import os
from typing import Self

from macaron.errors import CUEExpectationError, CUERuntimeError
from macaron.slsa_analyzer.provenance.expectations.cue import cue_validator
from macaron.slsa_analyzer.provenance.expectations.expectation import Expectation

logger: logging.Logger = logging.getLogger(__name__)


class CUEExpectation(Expectation):
    """A sub-class of the Expectation class to make CUE expectations."""

    @classmethod
    def make_expectation(cls, expectation_path: os.PathLike | str) -> Self | None:
        """Construct a CUE expectation from a CUE file.

        Note: we require the CUE expectation file to have a "target" field.

        Parameters
        ----------
        expectation_path: os.PathLike | str
            The path to the expectation file.

        Returns
        -------
        Self
            The instantiated expectation object.
        """
        logger.info("Generating an expectation from file %s", expectation_path)
        expectation: CUEExpectation = CUEExpectation(
            "CUE expectation has no ID",
            "CUE expectation has no description",
            expectation_path,
            "",
            None,
            None,
            "CUE",
        )

        try:
            with open(expectation_path, encoding="utf-8") as expectation_file:
                expectation.text = expectation_file.read()
                expectation.sha = str(hashlib.sha256(expectation.text.encode("utf-8")).hexdigest())
                expectation.target = cue_validator.get_target(expectation.text)
                expectation._validator = (  # pylint: disable=protected-access
                    lambda provenance: cue_validator.validate_expectation(expectation.text, provenance)
                )
        except (OSError, CUERuntimeError, CUEExpectationError) as error:
            logger.error("CUE expectation error: %s", error)
            return None

        # TODO remove type ignore once mypy adds support for Self.
        return expectation  # type: ignore
