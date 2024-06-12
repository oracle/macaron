# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the CycloneDX helper functions."""
import os
from pathlib import Path

import pytest
from cyclonedx.model.component import Component as CDXComponent

from macaron.config.defaults import defaults, load_defaults
from macaron.database.table_definitions import Analysis, Component, Repository
from macaron.dependency_analyzer.cyclonedx import CycloneDXParserError, DependencyInfo, deserialize_bom_json
from macaron.dependency_analyzer.cyclonedx_mvn import CycloneDxMaven
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool

RESOURCES_DIR = Path(__file__).parent.joinpath("resources")


def test_deserialize_bom_json(snapshot: list[str]) -> None:
    """Test deserializing a bom.json file."""
    # Deserialize a valid bom.json.
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
    ("build_tool_name", "child_boms", "recursive"),
    [
        ("maven", False, False),
        ("maven", False, True),
        ("maven", True, False),
        ("maven", True, True),
        ("gradle", False, False),
        ("gradle", False, True),
        ("gradle", True, False),
        ("gradle", True, True),
    ],
)
def test_get_dep_components_java(
    snapshot: list, build_tools: dict[str, BaseBuildTool], build_tool_name: str, child_boms: bool, recursive: bool
) -> None:
    """Test retrieving dependencies as components."""
    # Path to the root bom.json.
    root_bom_path = Path(RESOURCES_DIR, "bom_aws_parent.json")

    dep_analyzer = build_tools[build_tool_name].get_dep_analyzer()
    component = Component(
        purl="pkg:maven/io.micronaut.aws/aws-parent@4.0.0-SNAPSHOT?type=pom",
        analysis=Analysis(),
        repository=Repository(complete_name="github.com/micronaut-projects/micronaut-aws", fs_path=""),
    )

    # Path to the sub-project bom.json files.
    child_bom_paths = (
        [Path(RESOURCES_DIR, "bom_aws_child_1.json"), Path(RESOURCES_DIR, "bom_aws_child_2.json")]
        if child_boms
        else None
    )
    result_bom_refs = sorted(
        res.bom_ref.value
        for res in dep_analyzer.get_dep_components(
            target_component=component,
            root_bom_path=root_bom_path,
            child_bom_paths=child_bom_paths,
            recursive=recursive,
        )
        if res.bom_ref.value
    )
    assert snapshot == result_bom_refs


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
        "maven",
        "gradle",
    ],
)
def test_convert_components_to_artifacts_java(
    snapshot: dict[str, DependencyInfo], build_tools: dict[str, BaseBuildTool], build_tool_name: str
) -> None:
    """Test converting CycloneDX components using internal artifact representation."""
    # Path to the root bom.json.
    root_bom_path = Path(RESOURCES_DIR, "bom_aws_parent.json")

    # Disable repo finding to prevent remote calls during testing
    load_defaults(os.path.join(os.path.dirname(os.path.abspath(__file__)), "defaults.ini"))
    assert defaults.getboolean("repofinder.java", "find_repos") is False
    assert defaults.get_list("repofinder", "redirect_urls") == []

    dep_analyzer = build_tools[build_tool_name].get_dep_analyzer()
    component = Component(
        purl="pkg:maven/io.micronaut.aws/aws-parent@4.0.0-SNAPSHOT?type=pom",
        analysis=Analysis(),
        repository=Repository(complete_name="github.com/micronaut-projects/micronaut-aws", fs_path=""),
    )

    # Path to the sub-project bom.json files.
    child_bom_paths = [Path(RESOURCES_DIR, child) for child in ["bom_aws_child_1.json", "bom_aws_child_2.json"]]

    # Pass a root bom.json and two sub-project bom.json files in recursive mode.
    result = dep_analyzer.convert_components_to_artifacts(
        dep_analyzer.get_dep_components(
            target_component=component, root_bom_path=root_bom_path, child_bom_paths=child_bom_paths, recursive=True
        )
    )
    assert snapshot == result


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
    )

    # Pass the root bom.json.
    result = dep_analyzer.convert_components_to_artifacts(
        dep_analyzer.get_dep_components(target_component=component, root_bom_path=root_bom_path, recursive=True)
    )
    assert snapshot == result


@pytest.mark.parametrize(
    ("name", "build_tool_name"),
    [
        ("bom_no_group.json", "maven"),
        ("bom_no_version.json", "maven"),
        ("bom_no_group.json", "gradle"),
        ("bom_no_version.json", "gradle"),
    ],
)
def test_low_quality_bom(
    snapshot: dict[str, DependencyInfo], name: str, build_tools: dict[str, BaseBuildTool], build_tool_name: str
) -> None:
    """Test converting CycloneDX components when the quality of the BOM file is poor.

    E.g., a component misses a version or group.
    """
    # Path to the BOM file.
    bom_path = Path(RESOURCES_DIR, name)

    dep_analyzer = build_tools[build_tool_name].get_dep_analyzer()
    component = Component(
        purl="pkg:maven/com.amazonaws/aws-lambda-java-events@3.11.0?type=jar",
        analysis=Analysis(),
        repository=Repository(complete_name="github.com/aws/aws-lambda-java-libs", fs_path=""),
    )
    result = dep_analyzer.get_deps_from_sbom(bom_path, target_component=component)
    assert snapshot == result


@pytest.mark.parametrize(
    "build_tool_name",
    [
        "maven",
        "gradle",
    ],
)
def test_multiple_versions(
    snapshot: dict[str, DependencyInfo], build_tools: dict[str, BaseBuildTool], build_tool_name: str
) -> None:
    """Test converting CycloneDX components when there are multiple artifacts.

    Based on semantic versioning, version strings can contain alphabet characters.
    """
    # Path to the BOM file.
    bom_path = Path(RESOURCES_DIR, "bom_multi_versions.json")
    dep_analyzer = build_tools[build_tool_name].get_dep_analyzer()
    component = Component(
        purl="pkg:maven/com.amazonaws/aws-lambda-java-events@3.11.0?type=jar",
        analysis=Analysis(),
        repository=Repository(complete_name="github.com/aws/aws-lambda-java-libs", fs_path=""),
    )
    result = dep_analyzer.get_deps_from_sbom(bom_path, target_component=component)
    assert snapshot == result


def test_custom_sbom_name_with_maven() -> None:
    """Test reading cyclonedx maven sbom that was created using a custom name."""
    cyclonedx: CycloneDxMaven = CycloneDxMaven(
        "", "bom.json", "", defaults.get("dependency.resolver", "dep_tool_maven")
    )
    component = Component(
        purl="pkg:maven/com.example/cyclonedx-test@1.0-SNAPSHOT?type=jar",
        analysis=Analysis(),
        repository=None,
    )
    custom_bom_dir = RESOURCES_DIR.joinpath("sbom_name_tests")
    assert cyclonedx.collect_dependencies(str(custom_bom_dir.joinpath("single_named_sbom")), target_component=component)
    assert cyclonedx.collect_dependencies(
        str(custom_bom_dir.joinpath("single_named_sbom_with_children")), target_component=component
    )
    assert not cyclonedx.collect_dependencies(
        str(custom_bom_dir.joinpath("single_named_sbom_with_multiple_children")), target_component=component
    )
    assert not cyclonedx.collect_dependencies(
        str(custom_bom_dir.joinpath("multiple_named_sboms")), target_component=component
    )


@pytest.mark.parametrize(
    ("build_tool_name", "group", "name", "version", "expected_purl"),
    [
        ("pip", None, "django", "5.0.6", "pkg:pypi/django@5.0.6"),
        ("poetry", None, "django", "5.0.6", "pkg:pypi/django@5.0.6"),
        ("maven", "org.apache", "maven", "1.0.0", "pkg:maven/org.apache/maven@1.0.0"),
        ("gradle", "com.google", "guava", "32.1.2-jre", "pkg:maven/com.google/guava@32.1.2-jre"),
    ],
)
def test_get_purl_from_cdx_component(
    build_tools: dict[str, BaseBuildTool],
    build_tool_name: str,
    group: str | None,
    name: str,
    version: str,
    expected_purl: str,
) -> None:
    """Test constructing a PackageURL from a CycloneDX component."""
    dep_analyzer = build_tools[build_tool_name].get_dep_analyzer()
    component = CDXComponent(group=group, name=name, version=version)
    assert str(dep_analyzer.get_purl_from_cdx_component(component=component)) == expected_purl
