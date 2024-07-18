# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Test the check ``provenance_witness_l1_check``."""

import pytest

from macaron.slsa_analyzer.checks.provenance_witness_l1_check import verify_artifact_assets
from macaron.slsa_analyzer.package_registry.jfrog_maven_registry import (
    JFrogMavenAsset,
    JFrogMavenAssetMetadata,
    JFrogMavenRegistry,
)
from macaron.slsa_analyzer.provenance.intoto.v01 import InTotoV01Subject


@pytest.fixture(name="subjects")
def subjects_() -> list[InTotoV01Subject]:
    """Return the list of subjects in an example witness provenance."""
    return [
        {
            "name": "https://witness.dev/attestations/product/v0.1/file:target/boo-1.0.0.jar",
            "digest": {
                "sha256": "cbc8f554dbfa17e5c5873c425a09cb1488c2f784ac52340747a92b7ec0aaefba",
            },
        },
        {
            "name": "https://witness.dev/attestations/product/v0.1/file:sources/boo-1.0.0-sources.jar",
            "digest": {
                "sha256": "6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e",
            },
        },
        {
            "name": "https://witness.dev/attestations/product/v0.1/file:foo/bar/boo-1.0.0.jar",
            "digest": {
                "sha256": "d2238e45bb212fbe4a2e8e7dc160ffa123bacc5396899a039e973d2930eb4e41",
            },
        },
    ]


@pytest.mark.parametrize(
    ("artifact_assets"),
    [
        pytest.param(
            [
                JFrogMavenAsset(
                    name="boo-1.0.0.jar",
                    group_id="io.oracle.macaron",
                    artifact_id="boo",
                    version="1.0.0",
                    metadata=JFrogMavenAssetMetadata(
                        size_in_bytes=50,
                        sha256_digest="cbc8f554dbfa17e5c5873c425a09cb1488c2f784ac52340747a92b7ec0aaefba",
                        download_uri="https://artifactory.com/repo/io/oracle/macaron/boo/1.0.0/target/boo-1.0.0.jar",
                    ),
                    jfrog_maven_registry=JFrogMavenRegistry(),
                ),
                JFrogMavenAsset(
                    name="boo-1.0.0-sources.jar",
                    group_id="io.oracle.macaron",
                    artifact_id="boo",
                    version="1.0.0",
                    metadata=JFrogMavenAssetMetadata(
                        size_in_bytes=100,
                        sha256_digest="6f97fe2094bd50435d6fbb7a2f6c2638fe44e6af17cfff98ce111d0abfffe17e",
                        download_uri="https://artifactory.com/repo/io/oracle/macaron/boo/1.0.0/sources/boo-1.0.0-sources.jar",
                    ),
                    jfrog_maven_registry=JFrogMavenRegistry(),
                ),
            ],
            id="The assets list can match only a subset of subjects, as long as all assets in that list are verified.",
        ),
        pytest.param(
            [
                JFrogMavenAsset(
                    name="boo-1.0.0.jar",
                    group_id="io.oracle.macaron",
                    artifact_id="boo",
                    version="1.0.0",
                    metadata=JFrogMavenAssetMetadata(
                        size_in_bytes=50,
                        sha256_digest="cbc8f554dbfa17e5c5873c425a09cb1488c2f784ac52340747a92b7ec0aaefba",
                        download_uri="https://artifactory.com/repo/io/oracle/macaron/boo/1.0.0/target/boo-1.0.0.jar",
                    ),
                    jfrog_maven_registry=JFrogMavenRegistry(),
                ),
                JFrogMavenAsset(
                    name="boo-1.0.0.jar",
                    group_id="io.oracle.macaron",
                    artifact_id="boo",
                    version="1.0.0",
                    metadata=JFrogMavenAssetMetadata(
                        size_in_bytes=99,
                        sha256_digest="d2238e45bb212fbe4a2e8e7dc160ffa123bacc5396899a039e973d2930eb4e41",
                        download_uri="https://artifactory.com/repo/io/oracle/macaron/boo/1.0.0/foo/bar/boo-1.0.0.jar",
                    ),
                    jfrog_maven_registry=JFrogMavenRegistry(),
                ),
            ],
            id="Two assets can share the same file name but have different digests.",
        ),
    ],
)
def test_verify_artifact_assets(
    artifact_assets: list[JFrogMavenAsset],
    subjects: list[InTotoV01Subject],
) -> None:
    """Test the verify_artifact_assets function."""
    assert verify_artifact_assets(
        artifact_assets=artifact_assets,
        subjects=subjects,
    )


@pytest.mark.parametrize(
    ("artifact_assets"),
    [
        pytest.param(
            [
                JFrogMavenAsset(
                    name="boo-1.0.0.jar",
                    group_id="io.oracle.macaron",
                    artifact_id="boo",
                    version="1.0.0",
                    metadata=JFrogMavenAssetMetadata(
                        size_in_bytes=50,
                        sha256_digest="cbc8f554dbfa17e5c5873c425a09cb1488c2f784ac52340747a92b7ec0aaefba",
                        download_uri="https://artifactory.com/repo/io/oracle/macaron/boo/1.0.0/target/boo-1.0.0.jar",
                    ),
                    jfrog_maven_registry=JFrogMavenRegistry(),
                ),
                JFrogMavenAsset(
                    name="this-does-not-exist",
                    group_id="io.oracle.macaron",
                    artifact_id="boo",
                    version="1.0.0",
                    metadata=JFrogMavenAssetMetadata(
                        size_in_bytes=50,
                        sha256_digest="cbc8f554dbfa17e5c5873c425a09cb1488c2f784ac52340747a92b7ec0aaefba",
                        download_uri="https://artifactory.com/repo/io/oracle/macaron/boo/1.0.0/this-does-not-exist",
                    ),
                    jfrog_maven_registry=JFrogMavenRegistry(),
                ),
            ],
            id="An asset that fails verification lead to failed verification as a whole.",
        ),
    ],
)
def test_verify_invalid_artifact_assets(
    artifact_assets: list[JFrogMavenAsset],
    subjects: list[InTotoV01Subject],
) -> None:
    """Test the verify_artifact_assets function with invalid assets."""
    assert not verify_artifact_assets(
        artifact_assets=artifact_assets,
        subjects=subjects,
    )
