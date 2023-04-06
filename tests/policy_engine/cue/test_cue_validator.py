# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the CUE policy validator."""

import json
import os
from pathlib import Path

import pytest

from macaron.policy_engine.cue.cue_policy import CUEPolicy
from macaron.policy_engine.cue.cue_validator import get_target, validate_policy

RESOURCES_PATH = Path(__file__).parent.joinpath("resources")


@pytest.mark.parametrize(
    "policy_path",
    [
        os.path.join(RESOURCES_PATH, "invalid_policies", "1.cue"),
        os.path.join(RESOURCES_PATH, "invalid_policies", "2.cue"),
        os.path.join(RESOURCES_PATH, "invalid_policies", "no_file.cue"),
    ],
)
def test_make_policy(policy_path: str) -> None:
    """Test making policies from invalid CUE policy files.

    A CUE policy that misses "target" field is considered invalid.
    """
    assert not CUEPolicy.make_policy(policy_path=policy_path)


@pytest.mark.parametrize(
    ("policy_path", "expected"),
    [
        (os.path.join(RESOURCES_PATH, "valid_policies", "1.cue"), "urllib3/urllib3"),
        (os.path.join(RESOURCES_PATH, "valid_policies", "2.cue"), ""),
    ],
)
def test_get_target(policy_path: str, expected: str) -> None:
    """Test getting target from valid CUE policies."""
    policy = CUEPolicy.make_policy(policy_path=policy_path)
    if policy:
        assert get_target(policy.text) == expected


@pytest.mark.parametrize(
    ("policy_path", "prov_path", "expected"),
    [
        (
            os.path.join(RESOURCES_PATH, "valid_policies", "1.cue"),
            os.path.join(RESOURCES_PATH, "valid_provenances", "1.json"),
            True,
        ),
        (
            os.path.join(RESOURCES_PATH, "valid_policies", "1.cue"),
            os.path.join(RESOURCES_PATH, "valid_provenances", "2.json"),
            False,
        ),
        (
            os.path.join(RESOURCES_PATH, "valid_policies", "2.cue"),
            os.path.join(RESOURCES_PATH, "valid_provenances", "1.json"),
            False,
        ),
        (
            os.path.join(RESOURCES_PATH, "valid_policies", "2.cue"),
            os.path.join(RESOURCES_PATH, "valid_provenances", "2.json"),
            False,
        ),
    ],
)
def test_validate_policy(policy_path: str, prov_path: str, expected: bool) -> None:
    """Test validating CUE policies against provenances."""
    policy = CUEPolicy.make_policy(policy_path=policy_path)
    if policy:
        with open(prov_path, encoding="utf-8") as prov_file:
            provenance = json.load(prov_file)
        assert validate_policy(policy.text, provenance) == expected
