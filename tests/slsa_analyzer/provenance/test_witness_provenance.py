# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for witness provenance."""

import json
import os
from pathlib import Path

import pytest

from macaron.config.defaults import load_defaults
from macaron.slsa_analyzer.provenance.witness import (
    WitnessProvenanceSubject,
    WitnessVerifierConfig,
    extract_witness_provenance_subjects,
    is_witness_provenance_payload,
    load_witness_verifier_config,
)
from macaron.util import JsonType


@pytest.mark.parametrize(
    ("user_config_input", "expected_verifier_config"),
    [
        pytest.param(
            "",
            WitnessVerifierConfig(
                predicate_types={"https://witness.testifysec.com/attestation-collection/v0.1"},
                artifact_extensions={"jar"},
            ),
            id="Default config",
        ),
        pytest.param(
            """
            [provenance.witness]
            predicate_types =
                https://witness.testifysec.com/attestation-collection/v0.2
                https://witness.testifysec.com/attestation-collection/v0.3
            artifact_extensions =
                jar
                bom
            """,
            WitnessVerifierConfig(
                predicate_types={
                    "https://witness.testifysec.com/attestation-collection/v0.2",
                    "https://witness.testifysec.com/attestation-collection/v0.3",
                },
                artifact_extensions={"jar", "bom"},
            ),
            id="Valid config",
        ),
    ],
)
def test_load_witness_predicate_types(
    tmp_path: Path,
    user_config_input: str,
    expected_verifier_config: WitnessVerifierConfig,
) -> None:
    """Test the ``load_witness_predicate_types`` function."""
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)
    load_defaults(user_config_path)
    assert load_witness_verifier_config() == expected_verifier_config


@pytest.mark.parametrize(
    ("payload", "predicate_types", "expected_result"),
    [
        pytest.param(
            json.loads(
                """
            { "predicateType": "https://witness.testifysec.com/attestation-collection/v0.1" }
            """
            ),
            {"https://witness.testifysec.com/attestation-collection/v0.1"},
            True,
            id="Valid predicateType",
        ),
        pytest.param(
            json.loads(
                """
            { "predicateType": "https://witness.net/attestation-collection/v0.1" }
            """
            ),
            {"https://witness.testifysec.com/attestation-collection/v0.1"},
            False,
            id="Invalid predicateType",
        ),
        pytest.param(
            json.loads("{}"),
            ["https://witness.testifysec.com/attestation-collection/v0.1"],
            False,
            id="Missing predicateType",
        ),
    ],
)
def test_is_witness_provenance_payload(
    payload: dict[str, JsonType],
    predicate_types: set[str],
    expected_result: bool,
) -> None:
    """Test the ``is_witness_provenance_payload`` function."""
    assert is_witness_provenance_payload(payload, predicate_types) == expected_result


@pytest.mark.parametrize(
    ("payload", "expected_subjects"),
    [
        pytest.param(
            json.loads(
                """
{
    "subject": [
        {
            "name": "https://witness.dev/attestations/product/v0.1/file:target/jackson-annotations-2.9.9.jar",
            "digest": {
                "sha256": "6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e"
            }
        },
        {
            "name": "https://witness.dev/attestations/product/v0.1/file:foo/bar/baz.txt",
            "digest": {
                "sha256": "cbc8f554dbfa17e5c5873c425a09cb1488c2f784ac52340747a92b7ec0aaefba"
            }
        }
    ]
}
                """
            ),
            [
                WitnessProvenanceSubject(
                    subject_name=(
                        "https://witness.dev/attestations/product/v0.1/file:target/jackson-annotations-2.9.9.jar"
                    ),
                    sha256_digest="6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e",
                ),
                WitnessProvenanceSubject(
                    subject_name="https://witness.dev/attestations/product/v0.1/file:foo/bar/baz.txt",
                    sha256_digest="cbc8f554dbfa17e5c5873c425a09cb1488c2f784ac52340747a92b7ec0aaefba",
                ),
            ],
            id="Valid payload",
        ),
        pytest.param(json.loads("{}"), [], id="Missing 'subject'"),
        pytest.param(
            json.loads(
                """
            {
                "subject": {}
            }
            """
            ),
            [],
            id="Invalid 'subject' value",
        ),
        pytest.param(
            json.loads(
                """
{
    "subject": [
        {
            "name": "https://witness.dev/attestations/product/v0.1/file:target/jackson-annotations-2.9.9.jar",
            "digest": {
                "sha256": "6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e"
            }
        },
        {
            "name": "https://witness.dev/attestations/product/v0.1/file:foo/bar/baz.txt"
        },
        {
            "name": "https://witness.dev/attestations/product/v0.1/file:foo/bar/baz2.txt",
            "digest": {}
        },
        {
            "name": "https://witness.dev/attestations/product/v0.1/file:foo/bar/baz2.txt",
            "digest": {
                "sha256": {}
            }
        },
        {
            "name": [],
            "digest": {
                "sha256": "6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e"
            }
        },
        {},
        []
    ]
}
            """
            ),
            [
                WitnessProvenanceSubject(
                    subject_name=(
                        "https://witness.dev/attestations/product/v0.1/file:target/jackson-annotations-2.9.9.jar"
                    ),
                    sha256_digest="6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e",
                ),
            ],
            id="Malformed subject",
        ),
    ],
)
def test_extract_witness_provenances_subjects(
    payload: dict[str, JsonType],
    expected_subjects: list[WitnessProvenanceSubject],
) -> None:
    """Test the ``extract_witness_provenance_subjects`` function."""
    assert extract_witness_provenance_subjects(payload) == expected_subjects
