# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for VSA generation."""


import pytest

from macaron.vsa.vsa import get_components_passing_policy


@pytest.mark.parametrize(
    ("policy_result", "expected"),
    [
        pytest.param(
            {
                "component_satisfies_policy": [
                    [
                        "1",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
                "component_violates_policy": [],
            },
            {"pkg:github.com/slsa-framework/slsa-verifier@v2.0.0": 1},
            id="A single PURL satisfying policy",
        ),
        pytest.param(
            {
                "component_satisfies_policy": [
                    [
                        "1",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                    [
                        "2",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
                "component_violates_policy": [],
            },
            {"pkg:github.com/slsa-framework/slsa-verifier@v2.0.0": 2},
            id="Two occurrences of the same PURL both satisfying a policy",
        ),
        pytest.param(
            {
                "component_satisfies_policy": [
                    [
                        "1",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                    [
                        "2",
                        "pkg:github.com/slsa-framework/slsa-github-generator@v1.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
                "component_violates_policy": [],
            },
            {
                "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0": 1,
                "pkg:github.com/slsa-framework/slsa-github-generator@v1.0.0": 2,
            },
            id="Two different PURLs both satisfying a policy",
        ),
    ],
)
def test_valid_subject_verification_result(
    policy_result: dict,
    expected: dict[str, int],
) -> None:
    """Test the ``get_components_passing_policy`` in cases where there is a result."""
    assert get_components_passing_policy(policy_result) == expected


@pytest.mark.parametrize(
    ("policy_result"),
    [
        pytest.param(
            {
                "component_satisfies_policy": [],
                "component_violates_policy": [
                    [
                        "1",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
            },
            id="A single PURL violating policy",
        ),
        pytest.param(
            {
                "component_satisfies_policy": [
                    [
                        "9",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
                "component_violates_policy": [
                    [
                        "1000",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
            },
            id="Two occurrences of the same PURL, the one violating the policy is latest",
        ),
        pytest.param(
            {
                "component_satisfies_policy": [
                    [
                        "1000",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
                "component_violates_policy": [
                    [
                        "9",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
            },
            id="Two occurrences of the same PURL, the one satisfying the policy is latest",
        ),
        pytest.param(
            {
                "component_satisfies_policy": [],
                "component_violates_policy": [
                    [
                        "1",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                    [
                        "2",
                        "pkg:github.com/slsa-framework/slsa-github-generator@v1.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
            },
            id="Two different PURLs both violating a policy",
        ),
        pytest.param(
            {
                "component_satisfies_policy": [
                    [
                        "1",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
                "component_violates_policy": [
                    [
                        "2",
                        "pkg:github.com/slsa-framework/slsa-github-generator@v1.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
            },
            id="Two different PURLs, one satisfying and one violating a policy",
        ),
        pytest.param(
            {},
            id="Policy engine result is empty",
        ),
        pytest.param(
            {
                "component_satisfies_policy": [
                    [
                        "foo",
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
                "component_violates_policy": [],
            },
            id="Component id is not an auto-incremented number 1",
        ),
    ],
)
def test_invalid_subject_verification_result(
    policy_result: dict,
) -> None:
    """Test the ``get_components_passing_policy`` in cases where the result should be ``None``."""
    assert get_components_passing_policy(policy_result) is None
