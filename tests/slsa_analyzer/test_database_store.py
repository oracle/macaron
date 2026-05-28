# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for storing analysis results in Macaron's database."""

from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.database_store import get_policy_result_as_bool


def test_unknown_check_result_is_policy_pass() -> None:
    """Test UNKNOWN results are stored as passing for Datalog policy facts."""
    assert get_policy_result_as_bool(CheckResultType.PASSED)
    assert get_policy_result_as_bool(CheckResultType.UNKNOWN)
    assert not get_policy_result_as_bool(CheckResultType.FAILED)
