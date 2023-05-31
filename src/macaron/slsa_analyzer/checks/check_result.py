# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the CheckResult class for storing the result of a check."""
from enum import Enum
from typing import TypedDict

from sqlalchemy import Table
from sqlalchemy.orm import DeclarativeBase


class CheckResultType(str, Enum):
    """This class contains the types of a check result."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    # A check is skipped from another check's result.
    SKIPPED = "SKIPPED"
    # A check is disabled from the user configuration.
    DISABLED = "DISABLED"
    # The result of the check is unknown or Macaron cannot resolve the
    # implementation of this check.
    UNKNOWN = "UNKNOWN"


class CheckResult(TypedDict):
    """This class stores the result of a check in a dictionary."""

    check_id: str
    check_description: str
    # The string representations of the slsa requirements and their
    # corresponding slsa level.
    slsa_requirements: list[str]
    # If an element in the justification is a string,
    # it will be displayed as a string, if it is a mapping,
    # the value will be rendered as a hyperlink in the html report.
    justification: list[str | dict[str, str]]
    # human_readable_justification: str
    # result_values: dict[str, str | float | int] | list[dict[str, str | float | int]]
    result_tables: list[DeclarativeBase | Table]
    # recommendation: str
    result_type: CheckResultType
    confidence_score: float


class SkippedInfo(TypedDict):
    """This class stores the information about a skipped check."""

    check_id: str
    suppress_comment: str


def get_result_as_bool(check_result_type: CheckResultType) -> bool:
    """Return the CheckResultType as bool.

    This method returns True only if the result type is PASSED else it returns False.

    Parameters
    ----------
    check_result_type : CheckResultType
        The check result type to return the bool value.

    Returns
    -------
    bool
    """
    if check_result_type == CheckResultType.FAILED:
        return False

    return True
