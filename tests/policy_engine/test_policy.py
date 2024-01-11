# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the policies supported by the policy engine."""

import os
import subprocess  # nosec B404
from pathlib import Path

import pytest

from macaron.policy_engine.policy_engine import get_generated, run_souffle

POLICY_DIR = Path(__file__).parent.joinpath("resources").joinpath("policies")
POLICY_FILE = os.path.join(POLICY_DIR, "valid", "testpolicy.dl")
DATABASE_FILE = os.path.join(Path(__file__).parent.joinpath("resources", "facts", "macaron.db"))


@pytest.fixture()
def database_setup() -> None:
    """Prepare the database file."""
    if not os.path.exists(DATABASE_FILE):
        if os.path.exists(DATABASE_FILE + ".gz"):
            subprocess.run(["gunzip", "-k", DATABASE_FILE + ".gz"], check=True, shell=False)  # nosec B603 B607


def test_dump_prelude(database_setup) -> None:  # type: ignore # pylint: disable=unused-argument,redefined-outer-name
    """Test loading the policy from file."""
    res = str(get_generated(DATABASE_FILE))
    assert len(res) > 10


def test_eval_policy(database_setup) -> None:  # type: ignore # pylint: disable=unused-argument,redefined-outer-name
    """Test loading the policy from file."""
    with open(POLICY_FILE, encoding="utf-8") as file:
        policy_content = file.read()
    res = run_souffle(os.path.join(POLICY_FILE, DATABASE_FILE), policy_content)
    assert res == {
        "passed_policies": [["trusted_builder"]],
        "component_satisfies_policy": [
            [
                "1",
                "pkg:github.com/slsa-framework/slsa-verifier@fc50b662fcfeeeb0e97243554b47d9b20b14efac",
                "trusted_builder",
            ]
        ],
        "failed_policies": [["aggregate_l4"], ["aggregate_l2"]],
        "component_violates_policy": [
            [
                "1",
                "pkg:github.com/slsa-framework/slsa-verifier@fc50b662fcfeeeb0e97243554b47d9b20b14efac",
                "aggregate_l4",
            ],
            [
                "1",
                "pkg:github.com/slsa-framework/slsa-verifier@fc50b662fcfeeeb0e97243554b47d9b20b14efac",
                "aggregate_l2",
            ],
        ],
    }
