# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the check results."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType


class MockFacts(CheckFacts):
    """The ORM mapping for justifications in build_script check."""

    __tablename__ = "_test_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The name of the tool used to build.
    test_name: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    __mapper_args__ = {
        "polymorphic_identity": "_test_check",
    }


def test_check_result_justification() -> None:
    """Test that the check result justifications are sorted in a descending order based on the confidence score."""
    check_result_data = CheckResultData(
        result_tables=[
            MockFacts(test_name="foo", confidence=Confidence.LOW),
            MockFacts(test_name="bar", confidence=Confidence.HIGH),
            MockFacts(test_name="baz", confidence=Confidence.MEDIUM),
        ],
        result_type=CheckResultType.PASSED,
    )
    assert check_result_data.result_type == CheckResultType.PASSED
    assert check_result_data.justification_report == [
        (Confidence.HIGH, ["test_name: bar"]),
        (Confidence.MEDIUM, ["test_name: baz"]),
        (Confidence.LOW, ["test_name: foo"]),
    ]
