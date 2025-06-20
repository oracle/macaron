# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides a base class for provenance expectation verifiers."""

import json
import tempfile
from abc import abstractmethod
from collections.abc import Callable
from typing import Any, Self

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.errors import ExpectationRuntimeError
from macaron.slsa_analyzer.checks.check_result import JustificationType
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload

ExpectationFn = Callable[[Any], bool]


class Expectation(CheckFacts):
    """An intermediate abstract SQLAlchemy mapping for the expectation used to validate a target provenance."""

    # We would like to map different Expectation subclasses to individual tables. We need to leave this base class unmapped.
    __abstract__ = True

    #: The description.
    description: Mapped[str] = mapped_column(nullable=False)

    #: The path to the expectation file.
    path: Mapped[str] = mapped_column(nullable=False)

    #: The full repository name this expectation applies to.
    target: Mapped[str] = mapped_column(nullable=False)

    #: The full text content of the expectation.
    text: Mapped[str] = mapped_column(nullable=True)

    #: The sha256sum digest of the expectation.
    sha: Mapped[str] = mapped_column(nullable=True)

    #: The kind of expectation, e.g., CUE.
    expectation_type: Mapped[str] = mapped_column(nullable=False)

    #: The URL for the provenance asset that the expectation is verified against.
    asset_url: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Create an instance provenance expectation."""
        self._validator: ExpectationFn | None = None
        super().__init__(*args, **kwargs)

    @classmethod
    @abstractmethod
    def make_expectation(cls, expectation_path: str) -> Self | None:
        """Generate an expectation instance from an expectation file.

        Parameters
        ----------
        expectation_path : str
            The path to the expectation file.

        Returns
        -------
        Self | None
            The instantiated expectation object.
        """
        # SQLAlchemy does not allow to subclass abc.ABC. So, we need to raise `NotImplementedError`.
        raise NotImplementedError

    def __str__(self) -> str:
        return f"Expectation(description='{self.description}', path='{self.path}', target='{self.target}')"

    def validate(self, prov: InTotoPayload) -> bool:
        """Validate the provenance against this expectation.

        Parameters
        ----------
        prov : Any
            The provenance to validate.

        Returns
        -------
        bool

        Raises
        ------
        ExpectationRuntimeError
            If there are errors happened during the validation process.
        """
        if not self._validator:
            raise ExpectationRuntimeError(f"Unable to find the validator for expectation {self.path}")

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w+", delete=True) as prov_stmt_file:
            prov_stmt_file.write(json.dumps(prov.statement))
            # Rewind the file pointer before reading..
            prov_stmt_file.seek(0)
            return self._validator(prov_stmt_file.name)  # pylint: disable=not-callable

        raise ExpectationRuntimeError("Unable to validate the expectation.")
