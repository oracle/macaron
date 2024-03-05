# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for validation of in-toto attestation version 0.1."""

import pytest

from macaron.slsa_analyzer.provenance.intoto.errors import ValidateInTotoPayloadError
from macaron.slsa_analyzer.provenance.intoto.v1 import validate_intoto_statement
from macaron.util import JsonType


@pytest.mark.parametrize(
    ("payload"),
    [
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v1",
                "subject": [
                    {
                        "name": "foo.txt",
                        "uri": "sammple_sample_uri",
                    },
                ],
                "predicateType": "https://slsa.dev/provenance/v0.2",
            },
            id="With uri",
        ),
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v1",
                "subject": [
                    {
                        "name": "foo.txt",
                        "digest": {"sha256": "abcxyz123456"},
                    },
                ],
                "predicateType": "https://slsa.dev/provenance/v0.2",
            },
            id="With digest",
        ),
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v1",
                "subject": [
                    {"name": "foo.txt", "content": "content_content"},
                ],
                "predicateType": "https://slsa.dev/provenance/v0.2",
            },
            id="With content",
        ),
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v1",
                "subject": [
                    {
                        "name": "foo.txt",
                        "uri": "sample_sample_uri",
                        "digest": {"sha256": "abcxyz123456"},
                        "content": "content_content",
                    },
                ],
                "predicateType": "https://slsa.dev/provenance/v0.2",
            },
            id="With uri, digest, and content",
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
                "_type": "https://in-toto.io/Statement/v1",
                "predicateType": "https://slsa.dev/provenance/v0.2",
            },
            id="Missing 'subject'",
        ),
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v1",
                "subject": "subject",
                "predicateType": "https://slsa.dev/provenance/v0.2",
            },
            id="Invalid 'subject'",
        ),
        pytest.param(
            {
                "_type": "https://in-toto.io/Statement/v1",
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
                "_type": "https://in-toto.io/Statement/v1",
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
                "_type": "https://in-toto.io/Statement/v1",
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
