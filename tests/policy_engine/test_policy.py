# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the policy parser."""

import os
from pathlib import Path
from typing import Any, Callable
from unittest import TestCase

from hypothesis import given

from macaron.policy_engine.policy import InvalidPolicyError, Policy, PolicyFn, _gen_policy_func

from ..st import RECURSIVE_ST


class TestPolicyParser(TestCase):
    """This class tests the Policy Parser."""

    POLICY_DIR = Path(__file__).parent.joinpath("resources").joinpath("policies")

    class MockClass:
        """This class only exists in this test case."""

    def test_get_policy_from_file(self) -> None:
        """Test loading the policy from file."""
        assert not Policy.make_policy(os.path.join(self.POLICY_DIR, "invalid.yaml"))
        assert Policy.make_policy(os.path.join(self.POLICY_DIR, "slsa_verifier.yaml"))

    # pylint: disable=not-callable
    def test_validating_data(self) -> None:
        """Test validating data using the function returned by gen_policy_func."""

        # float('nan') is not equal to itself.
        assert not _gen_policy_func({"A": float("nan")})({"A": float("nan")})

        policy = {
            "A": {
                "B": {"C": {"D": 435223}},
                "F": [1, "foo", 3, 4],
                "G": "blah",
            }
        }
        policy_f: PolicyFn = _gen_policy_func(policy)

        assert not policy_f(None)
        assert not policy_f(float("nan"))
        assert not policy_f(self.MockClass())
        assert not policy_f(
            {
                "A": {
                    "B": {"C": {"D": 435223}},
                    "G": "blah",
                }
            }
        )

        # Different orders of elements in a dictionary do not affect the result.
        assert policy_f(
            {
                "A": {
                    "B": {"C": {"D": 435223}},
                    "G": "blah",
                    "F": [1, "foo", 3, 4],
                }
            }
        )

        # The order of elements in a list is important.
        assert not policy_f(
            {
                "A": {
                    "B": {"C": {"D": 435223}},
                    "G": "blah",
                    "F": [1, 3, "foo", 4],
                }
            }
        )

    @given(policy=RECURSIVE_ST)
    def test_gen_policy_func(self, policy: Any) -> None:
        """Test the gen_policy_func method"""
        policy_f = _gen_policy_func(policy)
        assert isinstance(policy_f, Callable)  # type:ignore

        with self.assertRaises(InvalidPolicyError):
            _gen_policy_func({"A": self.MockClass()})
