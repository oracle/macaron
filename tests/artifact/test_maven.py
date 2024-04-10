# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for types and utilities for Maven artifacts."""

import pytest
from packageurl import PackageURL

from macaron.artifact.maven import MavenSubjectPURLMatcher
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, validate_intoto_payload


@pytest.mark.parametrize(
    ("purl_str", "subject_index"),
    [
        pytest.param(
            "pkg:maven/com.fasterxml.jackson/jackson-annotations@2.9.9?type=jar",
            0,
            id="purl for jar artifact",
        ),
        pytest.param(
            "pkg:maven/com.fasterxml.jackson/jackson-annotations@2.9.9?type=javadoc",
            1,
            id="purl for javadoc artifact",
        ),
        pytest.param(
            "pkg:maven/com.fasterxml.jackson/jackson-annotations@2.9.9?type=java-source",
            2,
            id="purl for java source artifact",
        ),
        pytest.param(
            "pkg:maven/com.fasterxml.jackson/jackson-annotations@2.9.9?type=pom",
            3,
            id="purl for pom artifact",
        ),
    ],
)
def test_to_maven_artifact_subject(
    purl_str: str,
    subject_index: int,
) -> None:
    """Test constructing a ``MavenArtifact`` object from a given artifact name."""
    purl = PackageURL.from_string(purl_str)
    provenance_payload: InTotoPayload = validate_intoto_payload(
        {
            "_type": "https://in-toto.io/Statement/v0.1",
            "subject": [
                {
                    "name": "https://witness.dev/attestations/product/v0.1/file:target/jackson-annotations-2.9.9.jar",
                    "digest": {
                        "sha256": "6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e",
                    },
                },
                {
                    "name": "https://witness.dev/attestations/product/v0.1/file:target/jackson-annotations-2.9.9-javadoc.jar",
                    "digest": {
                        "sha256": "6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e",
                    },
                },
                {
                    "name": "https://witness.dev/attestations/product/v0.1/file:target/jackson-annotations-2.9.9-sources.jar",
                    "digest": {
                        "sha256": "6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e",
                    },
                },
                {
                    "name": "https://witness.dev/attestations/product/v0.1/file:target/jackson-annotations-2.9.9.pom",
                    "digest": {
                        "sha256": "6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e",
                    },
                },
                {
                    "name": "https://witness.dev/attestations/product/v0.1/file:target/foobar.txt",
                    "digest": {
                        "sha256": "6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e",
                    },
                },
            ],
            "predicateType": "https://witness.testifysec.com/attestation-collection/v0.1",
        }
    )
    assert (
        MavenSubjectPURLMatcher.get_subject_in_provenance_matching_purl(
            provenance_payload=provenance_payload,
            purl=purl,
        )
        == provenance_payload.statement["subject"][subject_index]
    )
