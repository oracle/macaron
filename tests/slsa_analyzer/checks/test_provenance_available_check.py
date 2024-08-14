# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the provenance available check."""

from pathlib import Path

from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.checks.provenance_available_check import ProvenanceAvailableCheck
from tests.conftest import MockAnalyzeContext


def test_provenance_available_check_(
    macaron_path: Path,
) -> None:
    """Test provenance available check."""
    check = ProvenanceAvailableCheck()
    ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir="")

    assert check.run_check(ctx).result_type == CheckResultType.FAILED
