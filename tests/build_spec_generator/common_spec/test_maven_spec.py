# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Maven build specification field resolution."""

from unittest.mock import patch

import pytest
from packageurl import PackageURL

from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpecDict
from macaron.build_spec_generator.common_spec.maven_spec import MavenBuildSpec

PURL_STRING = "pkg:maven/com.example/demo@1.0.0"


def _build_spec_dict(language_version: list[str]) -> BaseBuildSpecDict:
    """Return a minimal Maven build spec dict carrying the passed language version list."""
    return BaseBuildSpecDict(
        ecosystem="maven",
        purl=PURL_STRING,
        language="java",
        build_tools=["maven"],
        macaron_version="0.0.0",
        group_id="com.example",
        artifact_id="demo",
        version="1.0.0",
        language_version=list(language_version),
        build_commands=[
            {
                "build_tool": "maven",
                "build_config_path": "pom.xml",
                "command": ["mvn", "clean", "package"],
                "confidence_score": 1.0,
            }
        ],
    )


def _resolve(language_version: list[str], jdk_from_jar: str | None) -> list[str]:
    """Resolve a Maven build spec with the JAR lookup pinned, and return the resulting language version."""
    data = _build_spec_dict(language_version)
    with patch(
        "macaron.build_spec_generator.common_spec.maven_spec.find_jdk_version_from_central_maven_repo",
        return_value=jdk_from_jar,
    ):
        MavenBuildSpec(data).resolve_fields(PackageURL.from_string(PURL_STRING))
    return data["language_version"]


@pytest.mark.parametrize(
    ("existing", "jdk_from_jar", "expected"),
    [
        # The JAR manifest is the strongest evidence and wins whether or not the database
        # recorded a language version. The empty-list case is the ordinary one: core.py sets
        # "language_version" to [] whenever the database holds no recorded version.
        ([], "17", ["17"]),
        (["11"], "17", ["17"]),
        # No JAR evidence: fall back to what the database recorded, then to the default of 8.
        (["11"], None, ["11"]),
        ([], None, ["8"]),
    ],
)
def test_resolve_fields_selects_jdk_version(existing: list[str], jdk_from_jar: str | None, expected: list[str]) -> None:
    """The JDK read from the Maven Central JAR must not be discarded when the database recorded none."""
    assert _resolve(existing, jdk_from_jar) == expected
