# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for validation of in-toto attestation version 0.1."""

import pytest

from macaron.intoto.errors import ValidateInTotoPayloadError
from macaron.intoto.v01 import validate_intoto_statement, validate_intoto_subject
from macaron.util import JsonType


@pytest.mark.parametrize(
    ("payload"),
    [
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v0.1",
                "subject": [
                    {
                        "name": "foo.txt",
                        "digest": {"sha256": "abcxyz123456"},
                    },
                ],
                "predicateType": "https://slsa.dev/provenance/v0.2",
            },
            id="Without predicate",
        ),
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v0.1",
                "subject": [
                    {
                        "name": "foo.txt",
                        "digest": {"sha256": "abcxyz123456"},
                    },
                ],
                "predicateType": "https://slsa.dev/provenance/v0.2",
                "predicate": {
                    "builder": {
                        "id": "https://github.com/slsa-framework/slsa-github-generator/.github/workflows/builder_go_slsa3.yml@refs/tags/v1.5.0"  # noqa: B950
                    },
                    "buildType": "https://github.com/slsa-framework/slsa-github-generator/go@v1",
                },
            },
            id="With predicate",
        ),
    ],
)
def test_validate_valid_intoto_statement(
    payload: dict[str, JsonType],
) -> None:
    """Test validating valid in-toto statements."""
    assert validate_intoto_statement(payload) is True


@pytest.mark.parametrize(
    ("payload"),
    [
        pytest.param(
            {
                "subject": [
                    {
                        "name": "foo.txt",
                        "digest": {"sha256": "abcxyz123456"},
                    },
                ],
                "predicateType": "https://slsa.dev/provenance/v0.2",
            },
            id="Missing '_type'",
        ),
        pytest.param(
            {
                "_type": {},
                "subject": [
                    {
                        "name": "foo.txt",
                        "digest": {"sha256": "abcxyz123456"},
                    },
                ],
                "predicateType": "https://slsa.dev/provenance/v0.2",
            },
            id="Invalid '_type'",
        ),
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v0.1",
                "predicateType": "https://slsa.dev/provenance/v0.2",
            },
            id="Missing 'subject'",
        ),
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v0.1",
                "subject": "subject",
                "predicateType": "https://slsa.dev/provenance/v0.2",
            },
            id="Invalid 'subject'",
        ),
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v0.1",
                "subject": [
                    {
                        "name": "foo.txt",
                        "digest": {"sha256": "abcxyz123456"},
                    },
                ],
            },
            id="Missing 'predicateType'",
        ),
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v0.1",
                "subject": [
                    {
                        "name": "foo.txt",
                        "digest": {"sha256": "abcxyz123456"},
                    },
                ],
                "predicateType": {},
            },
            id="Invalid 'predicateType'",
        ),
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v0.1",
                "subject": [
                    {
                        "name": "foo.txt",
                        "digest": {"sha256": "abcxyz123456"},
                    },
                ],
                "predicateType": "https://slsa.dev/provenance/v0.2",
                "predicate": [],
            },
            id="Invalid 'predicate'",
        ),
    ],
)
def test_validate_invalid_intoto_statement(
    payload: dict[str, JsonType],
) -> None:
    """Test validating invalid in-toto statements."""
    with pytest.raises(ValidateInTotoPayloadError):
        validate_intoto_statement(payload)


@pytest.mark.parametrize(
    ("subject_json"),
    [
        pytest.param(
            [],
            id="Invalid subject entry",
        ),
        pytest.param(
            {
                "digest": {"sha256": "abcxyz123456"},
            },
            id="Missing 'name'",
        ),
        pytest.param(
            {
                "name": {},
                "digest": {"sha256": "abcxyz123456"},
            },
            id="Invalid 'name'",
        ),
        pytest.param(
            {
                "name": "foo.txt",
            },
            id="Missing 'digest'",
        ),
        pytest.param(
            {
                "name": "foo.txt",
                "digest": "digest",
            },
            id="Invalid 'digest' 1",
        ),
        pytest.param(
            {
                "name": "foo.txt",
                "digest": {"sha256": {}},
            },
            id="Invalid 'digest' 2",
        ),
    ],
)
def test_validate_invalid_subject(
    subject_json: JsonType,
) -> None:
    """Test validating invalid in-toto subjects."""
    with pytest.raises(ValidateInTotoPayloadError):
        validate_intoto_subject(subject_json)
