# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
Test the logic for dockerfile generation to rebuild PyPI packages.
"""

import pytest

from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpecDict, SpecBuildCommandDict
from macaron.build_spec_generator.dockerfile.pypi_dockerfile_output import gen_dockerfile


@pytest.fixture(name="pypi_build_spec")
def fixture_base_build_spec() -> BaseBuildSpecDict:
    """Create a base build spec object."""
    return BaseBuildSpecDict(
        {
            "macaron_version": "0.19.0",
            "group_id": None,
            "artifact_id": "cachetools",
            "version": "6.2.1",
            "git_repo": "https://github.com/tkem/cachetools",
            "git_tag": "ca7508fd56103a1b6d6f17c8e93e36c60b44ca25",
            "newline": "lf",
            "language_version": [">=3.9"],
            "ecosystem": "pypi",
            "purl": "pkg:pypi/cachetools@6.2.1",
            "language": "python",
            "has_binaries": False,
            "build_tools": ["pip"],
            "build_commands": [SpecBuildCommandDict(build_tool="pip", command=["python", "-m", "build"])],
            "build_requires": {"setuptools": "==80.9.0", "wheel": ""},
            "build_backends": ["setuptools.build_meta"],
            "upstream_artifacts": {
                "wheels": [
                    "https://files.pythonhosted.org/packages/96/c5/"
                    "1e741d26306c42e2bf6ab740b2202872727e0f606033c9dd713f8b93f5a8/cachetools-6.2.1-py3-none-any.whl"
                ],
                "sdist": [
                    "https://files.pythonhosted.org/packages/cc/7e/"
                    "b975b5814bd36faf009faebe22c1072a1fa1168db34d285ef0ba071ad78c/cachetools-6.2.1.tar.gz"
                ],
            },
        }
    )


def test_successful_generation(snapshot: str, pypi_build_spec: BaseBuildSpecDict) -> None:
    """Ensure that dockerfile is correctly generated for pypi_build_spec"""
    assert gen_dockerfile(pypi_build_spec) == snapshot
