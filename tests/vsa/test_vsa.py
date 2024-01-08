# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for VSA generation."""


import pytest

from macaron.vsa.vsa import VerificationResult, get_subject_verification_result


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
            ("pkg:github.com/slsa-framework/slsa-verifier@v2.0.0", VerificationResult.PASSED),
            id="A single PURL satisfying policy",
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
                ],
            },
            ("pkg:github.com/slsa-framework/slsa-verifier@v2.0.0", VerificationResult.FAILED),
            id="A single PURL violating policy",
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
            ("pkg:github.com/slsa-framework/slsa-verifier@v2.0.0", VerificationResult.PASSED),
            id="Two occurrences of the same PURL both satisfying a policy",
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
                        "pkg:github.com/slsa-framework/slsa-verifier@v2.0.0",
                        "slsa_verifier_policy",
                    ],
                ],
            },
            ("pkg:github.com/slsa-framework/slsa-verifier@v2.0.0", VerificationResult.FAILED),
            id="Two occurrences of the same PURL both violating a policy",
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
            ("pkg:github.com/slsa-framework/slsa-verifier@v2.0.0", VerificationResult.PASSED),
            id="Two occurrences of the same PURL, the one satisfying the policy is latest",
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
            ("pkg:github.com/slsa-framework/slsa-verifier@v2.0.0", VerificationResult.FAILED),
            id="Two occurrences of the same PURL, the one violating the policy is latest",
        ),
    ],
)
def test_valid_subject_verification_result(
    policy_result: dict,
    expected: tuple[str, VerificationResult],
) -> None:
    """Test the ``get_subject_verification_result`` in cases where there is a result."""
    assert get_subject_verification_result(policy_result) == expected


@pytest.mark.parametrize(
    ("policy_result"),
    [
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
            id="Two different PURLs both satisfying a policy",
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
    ],
)
def test_invalid_subject_verification_result(
    policy_result: dict,
) -> None:
    """Test the ``get_subject_verification_result`` in cases where the result should be ``None``."""
    assert get_subject_verification_result(policy_result) is None
