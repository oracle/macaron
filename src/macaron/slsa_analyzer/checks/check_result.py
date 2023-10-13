# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the CheckResult class for storing the result of a check."""
from dataclasses import dataclass
from enum import Enum
from typing import TypedDict

from sqlalchemy.orm import DeclarativeBase

from macaron.slsa_analyzer.provenance.expectations.expectation import Expectation
from macaron.slsa_analyzer.slsa_req import BUILD_REQ_DESC, ReqName

Justification = list[str | dict[str, str]]
ResultTables = list[DeclarativeBase | Expectation]


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


@dataclass
class CheckInfo:
    """This class identifies and describes a check."""

    check_id: str
    check_description: str
    eval_reqs: list[ReqName]


@dataclass
class CheckResultData:
    """This class stores the result of a check."""

    # If an element in the justification is a string,
    # it will be displayed as a string, if it is a mapping,
    # the value will be rendered as a hyperlink in the html report.
    justification: Justification
    # human_readable_justification: str
    # result_values: dict[str, str | float | int] | list[dict[str, str | float | int]]
    result_tables: ResultTables
    # recommendation: str
    result_type: CheckResultType


@dataclass
class CheckResult:
    """This class stores the result of a check, including the description of the check that produced it."""

    check: CheckInfo
    result: CheckResultData

    def get_dict(self) -> dict:
        """Get a flattened dictionary representation for this CheckResult.

        Returns
        -------
        dict
        """
        return {
            "check_id": self.check.check_id,
            "check_description": self.check.check_description,
            "slsa_requirements": [str(BUILD_REQ_DESC.get(req)) for req in self.check.eval_reqs],
            "justification": self.result.justification,
            "result_tables": self.result.result_tables,
            "result_type": self.result.result_type,
        }


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
    if check_result_type in (CheckResultType.FAILED, CheckResultType.UNKNOWN):
        return False

    return True
