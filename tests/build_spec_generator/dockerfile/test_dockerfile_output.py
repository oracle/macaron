# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
Test the logic to dispatch dockerfile generation
"""

import pytest

from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpecDict
from macaron.build_spec_generator.dockerfile import dockerfile_output
from macaron.errors import GenerateBuildSpecError


@pytest.fixture(name="maven_build_spec")
def fixture_base_build_spec() -> BaseBuildSpecDict:
    """Create a base build spec object."""
    return BaseBuildSpecDict(
        {
            "macaron_version": "1.0.0",
            "ecosystem": "maven",
            "language": "java",
            "group_id": "com.oracle",
            "artifact_id": "example-artifact",
            "version": "1.2.3",
            "git_repo": "https://github.com/oracle/example-artifact.git",
            "git_tag": "sampletag",
            "build_tools": ["maven"],
            "newline": "lf",
            "language_version": ["17"],
            "build_commands": [["mvn", "package"]],
            "purl": "pkg:maven/com.oracle/example-artifact@1.2.3",
        }
    )


def test_dispatch_error(maven_build_spec: BaseBuildSpecDict) -> None:
    """Ensure that dispatching for unsupported ecosystem fails"""
    with pytest.raises(GenerateBuildSpecError):
        dockerfile_output.gen_dockerfile(maven_build_spec)
