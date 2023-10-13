# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides a base class for provenance expectation verifiers."""

from collections.abc import Callable
from typing import Any, Self

from sqlalchemy.orm import Mapped, mapped_column

from macaron.errors import ExpectationRuntimeError
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload

ExpectationFn = Callable[[Any], bool]


# pylint: disable=invalid-name
class Expectation:
    """The SQLAlchemy mixin for the expectation used to validate a target provenance."""

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Create an instance provenance expectation."""
        self._validator: ExpectationFn | None = None
        super().__init__(*args, **kwargs)

    @classmethod
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
        raise NotImplementedError()

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
            raise ExpectationRuntimeError(f"Cannot find the validator for expectation {self.path}")

        return self._validator(prov.statement)  # pylint: disable=not-callable
