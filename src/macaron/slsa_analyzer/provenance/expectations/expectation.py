# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides a base class for provenance expectation verifiers."""

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Self

from macaron.database.table_definitions import PolicyTable
from macaron.errors import ExpectationRuntimeError
from macaron.util import JsonType

ExpectationFn = Callable[[Any], bool]


# pylint: disable=invalid-name
@dataclass
class Expectation:
    """The expectation is used to validate a target provenance.

    Parameters
    ----------
    ID : str
        The ID of the expectation.
    description : str
        The description.
    path: os.PathLike | str
        The path to the expectation file.
    target: str
        The full repository name this expectation applies to.
    text: str | None
        The full text content of the expectation.
    sha: str | None
        The sha256sum digest of the expectation.
    expectation_type: str
        The kind of expectation, e.g., CUE
    """

    ID: str
    description: str
    path: os.PathLike | str
    target: str
    text: str | None
    sha: str | None
    expectation_type: str
    _validator: ExpectationFn | None = field(default=None)

    def get_expectation_table(self) -> PolicyTable:
        """Get the bound ORM object for the policy."""
        return PolicyTable(
            policy_id=self.ID,
            description=self.description,
            policy_type=self.expectation_type,
            sha=self.sha,
            text=self.text,
        )

    @classmethod
    def make_expectation(cls, expectation_path: os.PathLike | str) -> Self | None:
        """Generate an expectation instance from an expectation file.

        Parameters
        ----------
        expectation_path : os.PathLike
            The path to the expectation file.

        Returns
        -------
        Self | None
            The instantiated expectation object.
        """
        raise NotImplementedError()

    def __str__(self) -> str:
        return f"Expectation(id='{self.ID}', description='{self.description}', path='{self.path}')"

    def validate(self, prov: JsonType) -> bool:
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
            raise ExpectationRuntimeError(f"Cannot find the validator for expectation {self.ID}")

        return self._validator(prov)  # pylint: disable=not-callable
