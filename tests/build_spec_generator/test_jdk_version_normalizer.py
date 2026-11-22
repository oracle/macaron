# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the tests for the jdk version normalizer module."""

import pytest

from macaron.build_spec_generator.common_spec.jdk_version_normalizer import normalize_jdk_version


@pytest.mark.parametrize(
    ("version_string", "expected"),
    [
        pytest.param(
            "1.8.0_523",
            "8",
            id="1.x_with_patch_version",
        ),
        pytest.param(
            "1.8",
            "8",
            id="1.x_without_patch_version",
        ),
        pytest.param(
            "11.0.1",
            "11",
            id="major_number_stands_first_with_patch_version",
        ),
        pytest.param(
            "11.0",
            "11",
            id="major_number_stands_first_without_patch_version",
        ),
        pytest.param(
            "11",
            "11",
            id="just_the_major_version",
        ),
        pytest.param(
            "8 (Azul Systems Inc. 25.282-b08)",
            "8",
            id="major_follows_with_text",
        ),
        pytest.param(
            "19-ea",
            "19",
            id="major_follows_with_text",
        ),
        # https://github.com/jboss-logging/jboss-logging/blob/25ad85c9cecf5a2f79db9a4d077221ed087e4ef5/.github/workflows/ci.yml#L46
        pytest.param(
            "22-ea",
            "22",
            id="pkg_maven_org.jboss.logging_jboss-logging_3.6.1.Final",
        ),
        # JDK 25 and later were released after the original list of supported versions was written.
        # Build-Jdk-Spec: 25 in the MANIFEST.MF of org.apache.commons:commons-lang3:3.20.0 on Maven Central.
        pytest.param(
            "25",
            "25",
            id="pkg_maven_org.apache.commons_commons-lang3_3.20.0",
        ),
        pytest.param(
            "25.0.1",
            "25",
            id="jdk_25_with_patch_version",
        ),
        pytest.param(
            "26-ea",
            "26",
            id="jdk_26_early_access",
        ),
        pytest.param(
            "1.4.2_19",
            None,
            id="unsupported_old_version",
        ),
        pytest.param(
            "unknown",
            None,
            id="no_version_number",
        ),
    ],
)
def test_jdk_version_normalizer(version_string: str, expected: str | None) -> None:
    """Test the jdk_version_normalizer function."""
    assert normalize_jdk_version(version_string) == expected
