# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the CUE expectation validator."""

import os
from pathlib import Path

import pytest

from macaron.errors import CUERuntimeError
from macaron.slsa_analyzer.provenance.expectations.cue import CUEExpectation
from macaron.slsa_analyzer.provenance.expectations.cue.cue_validator import get_target, validate_expectation

EXPECT_RESOURCE_PATH = Path(__file__).parent.joinpath("resources")
PROV_RESOURCE_PATH = Path(__file__).parent.parent.parent.joinpath("resources")
PACKAGE_URLLIB3 = "pkg:github.com/urllib3/urllib3"


@pytest.mark.parametrize(
    "expectation_path",
    [
        os.path.join(EXPECT_RESOURCE_PATH, "invalid_expectations", "invalid.cue"),
        os.path.join(EXPECT_RESOURCE_PATH, "invalid_expectations", "urllib3_INVALID.cue"),
        os.path.join(EXPECT_RESOURCE_PATH, "invalid_expectations", "no_file.cue"),
    ],
)
def test_make_expectation(expectation_path: str) -> None:
    """Test making expectations from invalid CUE expectation files.

    A CUE expectation that misses "target" field is considered invalid.
    """
    assert not CUEExpectation.make_expectation(expectation_path=expectation_path)


@pytest.mark.parametrize(
    ("expectation_path", "expected"),
    [
        (os.path.join(EXPECT_RESOURCE_PATH, "valid_expectations", "urllib3_PASS.cue"), PACKAGE_URLLIB3),
    ],
)
def test_get_target(expectation_path: str, expected: str) -> None:
    """Test getting target from valid CUE expectations."""
    assert get_target(expectation_path) == expected


@pytest.mark.parametrize(
    "expectation_path",
    [
        os.path.join(EXPECT_RESOURCE_PATH, "valid_expectations", "urllib3_FAIL.cue"),
    ],
)
def test_no_target(expectation_path: str) -> None:
    """Test getting target from valid CUE expectations that misses a target."""
    with pytest.raises(CUERuntimeError):
        get_target(expectation_path)


@pytest.mark.parametrize(
    ("expectation_path", "prov_path", "expected"),
    [
        (
            os.path.join(EXPECT_RESOURCE_PATH, "valid_expectations", "urllib3_PASS.cue"),
            os.path.join(PROV_RESOURCE_PATH, "valid_provenances", "urllib3_decoded_PASS.json"),
            True,
        ),
        (
            os.path.join(EXPECT_RESOURCE_PATH, "valid_expectations", "urllib3_PASS.cue"),
            os.path.join(PROV_RESOURCE_PATH, "valid_provenances", "urllib3_decoded_FAIL.json"),
            False,
        ),
        (
            os.path.join(EXPECT_RESOURCE_PATH, "valid_expectations", "urllib3_FAIL.cue"),
            os.path.join(PROV_RESOURCE_PATH, "valid_provenances", "urllib3_decoded_PASS.json"),
            False,
        ),
        (
            os.path.join(EXPECT_RESOURCE_PATH, "valid_expectations", "urllib3_FAIL.cue"),
            os.path.join(PROV_RESOURCE_PATH, "valid_provenances", "urllib3_decoded_FAIL.json"),
            False,
        ),
    ],
)
def test_validate_expectation(expectation_path: str, prov_path: str, expected: bool) -> None:
    """Test validating CUE expectations against provenances."""
    assert validate_expectation(expectation_path, prov_path) == expected
