# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides CUE expectation implementations.

A CUE expectation is constructed from an input file in CUE language provided to Macaron to check the content of a provenance.

To know more about the CUE language, see https://cuelang.org/
"""

import hashlib
import logging
import os
from typing import Self

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from macaron.errors import CUEExpectationError, CUERuntimeError
from macaron.slsa_analyzer.checks.check_result import Confidence
from macaron.slsa_analyzer.provenance.expectations.cue import cue_validator
from macaron.slsa_analyzer.provenance.expectations.expectation import Expectation

logger: logging.Logger = logging.getLogger(__name__)


class CUEExpectation(Expectation):
    """ORM Class for an expectation."""

    __tablename__ = "_cue_expectation"

    #: The primary key, which is also a foreign key to the base check table.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The polymorphic inheritance configuration.
    __mapper_args__ = {
        "polymorphic_identity": "_cue_expectation",
    }

    @classmethod
    def make_expectation(cls, expectation_path: str) -> Self | None:
        """Construct a CUE expectation from a CUE file.

        Note: we require the CUE expectation file to have a "target" field.

        Parameters
        ----------
        expectation_path: str
            The path to the expectation file.

        Returns
        -------
        Self
            The instantiated expectation object.
        """
        logger.info("Generating an expectation from file %s", os.path.relpath(expectation_path, os.getcwd()))
        expectation: CUEExpectation = CUEExpectation(
            description="CUE expectation",
            path=expectation_path,
            target="",
            expectation_type="CUE",
            confidence=Confidence.HIGH,
        )

        try:
            with open(expectation_path, encoding="utf-8") as expectation_file:
                expectation.text = expectation_file.read()
                expectation.sha = str(hashlib.sha256(expectation.text.encode("utf-8")).hexdigest())
                expectation.target = cue_validator.get_target(expectation_path)
                expectation._validator = (  # pylint: disable=protected-access
                    lambda provenance_path: cue_validator.validate_expectation(expectation_path, provenance_path)
                )
        except (OSError, CUERuntimeError, CUEExpectationError) as error:
            logger.error("CUE expectation error: %s", error)
            return None

        # TODO remove type ignore once mypy adds support for Self.
        return expectation  # type: ignore
