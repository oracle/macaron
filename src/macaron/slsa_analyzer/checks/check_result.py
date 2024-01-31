# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the CheckResult class for storing the result of a check."""
from dataclasses import dataclass
from enum import Enum
from heapq import heappush
from typing import TypedDict

from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.slsa_req import BUILD_REQ_DESC, ReqName


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


class Confidence(float, Enum):
    """This class contains confidence score for a check result.

    The scores must be in [0.0, 1.0].
    """

    #: A high confidence score.
    HIGH = 1.0

    #: A medium confidence score.
    MEDIUM = 0.7

    #: A low confidence score.
    LOW = 0.5


class JustificationType(str, Enum):
    """This class contains the type of a justification that will be used in creating the HTML report."""

    #: If a justification has a text type, it will be added as a plain text.
    TEXT = "text"

    #: If a justification has a href type, it will be added as a hyperlink.
    HREF = "href"


@dataclass(frozen=True)
class CheckInfo:
    """This class identifies and describes a check."""

    #: The id of the check.
    check_id: str

    #: The description of the check.
    check_description: str

    #: The list of SLSA requirements that this check addresses.
    eval_reqs: list[ReqName]


@dataclass(frozen=True)
class CheckResultData:
    """This class stores the result of a check."""

    #: List of result tables produced by the check.
    result_tables: list[CheckFacts]

    #: Result type of the check (e.g. PASSED).
    result_type: CheckResultType

    @property
    def justification_report(self) -> list[tuple[Confidence, list]]:
        """
        Return the list of justifications for the check result generated from the tables in the database.

        Note that the elements in the justification will be rendered different based on their types:

        * a :class:`JustificationType.TEXT` element is displayed in plain text in the HTML report.
        * a :class:`JustificationType.HREF` element is rendered as a hyperlink in the HTML report.

        Return
        ------
        list[tuple[Confidence, list]]
        """
        # Interestingly, mypy cannot infer the type of elements later at `heappush` if we specify
        # list[tuple[Confidence, list]]. But still, it insists on specifying the `list` type here.
        justification_list: list = []
        for result in self.result_tables:
            # The HTML report generator requires the justification elements that need to be rendered in HTML
            # to be passed as a dictionary as key-value pairs. The elements that need to be displayed in plain
            # text should be passed as string values.
            dict_elements: dict[str, str] = {}
            list_elements: list[str | dict] = []

            # Look for columns that are have "justification" metadata.
            for col in result.__table__.columns:
                column_value = getattr(result, col.name)
                if col.info.get("justification") and column_value:
                    if col.info.get("justification") == JustificationType.HREF:
                        dict_elements[col.name] = column_value
                    elif col.info.get("justification") == JustificationType.TEXT:
                        list_elements.append(f"{col.name}: {column_value}")

            # Add the dictionary elements to the list of justification elements.
            if dict_elements:
                list_elements.append(dict_elements)

            # Use heapq to always keep the justification with the highest confidence score in the first element.
            if list_elements:
                heappush(justification_list, (result.confidence, list_elements))

        # If there are no justifications available, return a default "Not Available" one.
        if not justification_list:
            return [(Confidence.HIGH, ["Not Available."])]

        return justification_list


@dataclass(frozen=True)
class CheckResult:
    """This class stores the result of a check, including the description of the check that produced it."""

    #: Info about the check that produced these results.
    check: CheckInfo

    #: The results produced by the check.
    result: CheckResultData

    def get_summary(self) -> dict:
        """Get a flattened dictionary representation for this CheckResult, in a format suitable for the output report.

        The SLSA requirements, in particular, are translated into a list of their textual descriptions, to be suitable
        for display to users in the output report (as opposed to the internal representation as a list of enum identifiers).

        Returns
        -------
        dict
        """
        return {
            "check_id": self.check.check_id,
            "check_description": self.check.check_description,
            "slsa_requirements": [str(BUILD_REQ_DESC.get(req)) for req in self.check.eval_reqs],
            # The justification report is stored in a heapq where the first element has the highest confidence score.
            "justification": self.result.justification_report[0][1],
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
