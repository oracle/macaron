# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the CycloneDX helper functions."""
from pathlib import Path

import pytest
from cyclonedx.model.component import Component as CDXComponent

from macaron.database.table_definitions import Analysis, Component, RepoFinderMetadata, Repository
from macaron.dependency_analyzer.cyclonedx import (
    CycloneDXParserError,
    DependencyAnalyzer,
    DependencyInfo,
    deserialize_bom_json,
)
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool

RESOURCES_DIR = Path(__file__).parent.joinpath("resources")


def test_deserialize_bom_json(snapshot: list[str]) -> None:
    """Test deserializing a bom.json file."""
    # Deserialize a valid bom.json.
    # Note that serializing the Bom object and compare against the original bom would be an ideal test,
    # but cyclonedx took a really long time to finish serializing (could be a bug).
    # So, we compare the resolved components as a proxy.
    path = Path(RESOURCES_DIR, "valid_bom.json")
    bom = deserialize_bom_json(path)
    assert snapshot == [str(cmp.bom_ref) for cmp in bom.components if isinstance(cmp, CDXComponent)]

    # Deserialize a bom.json that does not exist.
    with pytest.raises(CycloneDXParserError):
        deserialize_bom_json(Path(RESOURCES_DIR, "does_not_exist"))

    # Deserialize an invalid bom.json.
    with pytest.raises(CycloneDXParserError):
        deserialize_bom_json(Path(RESOURCES_DIR, "invalid_bom.json"))

    # Deserialize an invalid JSON file.
    with pytest.raises(CycloneDXParserError):
        deserialize_bom_json(Path(RESOURCES_DIR, "invalid_json.json"))


@pytest.mark.parametrize(
    ("build_tool_name", "recursive"),
    [
        ("pip", False),
        ("pip", True),
        ("poetry", False),
        ("poetry", True),
    ],
)
def test_get_dep_components_python(
    snapshot: list, build_tools: dict[str, BaseBuildTool], build_tool_name: str, recursive: bool
) -> None:
    """Test retrieving dependencies as components."""
    # Path to the root bom.json.
    root_bom_path = Path(RESOURCES_DIR, "bom_requests.json")

    dep_analyzer = build_tools[build_tool_name].get_dep_analyzer()
    component = Component(
        purl="pkg:pypi/requests@2.31.0",
        analysis=Analysis(),
        repository=Repository(complete_name="github.com/psf/requests", fs_path=""),
        repo_finder_metadata=RepoFinderMetadata(),
    )

    # Path to the sub-project bom.json files.
    result_bom_refs = sorted(
        res.bom_ref.value
        for res in dep_analyzer.get_dep_components(
            target_component=component, root_bom_path=root_bom_path, recursive=recursive
        )
        if res.bom_ref.value
    )
    assert snapshot == result_bom_refs


@pytest.mark.parametrize(
    "build_tool_name",
    [
        "pip",
        "poetry",
    ],
)
def test_convert_components_to_artifacts_python(
    snapshot: dict[str, DependencyInfo], build_tools: dict[str, BaseBuildTool], build_tool_name: str
) -> None:
    """Test converting CycloneDX components using internal artifact representation."""
    # Path to the root bom.json.
    root_bom_path = Path(RESOURCES_DIR, "bom_requests.json")

    dep_analyzer = build_tools[build_tool_name].get_dep_analyzer()
    component = Component(
        purl="pkg:pypi/requests@2.31.0",
        analysis=Analysis(),
        repository=Repository(complete_name="github.com/psf/requests", fs_path=""),
        repo_finder_metadata=RepoFinderMetadata(),
    )

    # Pass the root bom.json.
    result = dep_analyzer.convert_components_to_artifacts(
        dep_analyzer.get_dep_components(target_component=component, root_bom_path=root_bom_path, recursive=True),
        purl_type=component.namespace,
    )
    assert snapshot == result


@pytest.mark.parametrize(
    "name",
    [
        "bom_no_group.json",
        "bom_no_version.json",
    ],
)
def test_low_quality_bom(snapshot: dict[str, DependencyInfo], name: str) -> None:
    """Test converting CycloneDX components when the quality of the BOM file is poor.

    E.g., a component misses a version or group.
    """
    # Path to the BOM file.
    bom_path = Path(RESOURCES_DIR, name)

    component = Component(
        purl="pkg:maven/com.amazonaws/aws-lambda-java-events@3.11.0?type=jar",
        analysis=Analysis(),
        repository=Repository(complete_name="github.com/aws/aws-lambda-java-libs", fs_path=""),
        repo_finder_metadata=RepoFinderMetadata(),
    )
    result = DependencyAnalyzer.get_deps_from_sbom(bom_path, target_component=component)
    assert snapshot == result


def test_multiple_versions(snapshot: dict[str, DependencyInfo]) -> None:
    """Test converting CycloneDX components when there are multiple artifacts.

    Based on semantic versioning, version strings can contain alphabet characters.
    """
    # Path to the BOM file.
    bom_path = Path(RESOURCES_DIR, "bom_multi_versions.json")
    component = Component(
        purl="pkg:maven/com.amazonaws/aws-lambda-java-events@3.11.0?type=jar",
        analysis=Analysis(),
        repository=Repository(complete_name="github.com/aws/aws-lambda-java-libs", fs_path=""),
        repo_finder_metadata=RepoFinderMetadata(),
    )
    result = DependencyAnalyzer.get_deps_from_sbom(bom_path, target_component=component)
    assert snapshot == result


@pytest.mark.parametrize(
    ("purl_type", "group", "name", "version", "expected_purl"),
    [
        ("pypi", None, "django", "5.0.6", "pkg:pypi/django@5.0.6"),
        ("maven", "org.apache", "maven", "1.0.0", "pkg:maven/org.apache/maven@1.0.0"),
        ("maven", "com.google", "guava", "32.1.2-jre", "pkg:maven/com.google/guava@32.1.2-jre"),
    ],
)
def test_get_purl_from_cdx_component(
    purl_type: str,
    group: str | None,
    name: str,
    version: str,
    expected_purl: str,
) -> None:
    """Test constructing a PackageURL from a CycloneDX component."""
    component = CDXComponent(group=group, name=name, version=version)
    assert (
        str(DependencyAnalyzer.get_purl_from_cdx_component(component=component, purl_type=purl_type)) == expected_purl
    )
