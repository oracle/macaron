# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the CycloneDX helper functions."""
import os
from pathlib import Path

import pytest

from macaron.config.defaults import defaults, load_defaults
from macaron.dependency_analyzer.cyclonedx import (
    CycloneDXParserError,
    convert_components_to_artifacts,
    deserialize_bom_json,
    get_dep_components,
    get_deps_from_sbom,
)
from macaron.dependency_analyzer.cyclonedx_mvn import CycloneDxMaven
from macaron.dependency_analyzer.dependency_resolver import DependencyInfo

RESOURCES_DIR = Path(__file__).parent.joinpath("resources")


def test_deserialize_bom_json(snapshot: dict) -> None:
    """Test deserializing a bom.json file."""
    # Deserialize a valid bom.json.
    path = Path(RESOURCES_DIR, "valid_bom.json")
    assert snapshot == deserialize_bom_json(path)

    # Deserialize a bom.json that does not exist.
    with pytest.raises(CycloneDXParserError):
        deserialize_bom_json(Path(RESOURCES_DIR, "does_not_exist"))

    # Deserialize an invalid bom.json.
    with pytest.raises(CycloneDXParserError):
        deserialize_bom_json(Path(RESOURCES_DIR, "invalid_bom.json"))


@pytest.mark.parametrize(
    ("child_boms", "recursive"),
    [
        (False, False),
        (False, True),
        (True, False),
        (True, True),
    ],
)
def test_get_dep_components(snapshot: list, child_boms: bool, recursive: bool) -> None:
    """Test retrieving dependencies as components."""
    # Path to the root bom.json.
    root_bom_path = Path(RESOURCES_DIR, "root_bom.json")

    # Path to the sub-project bom.json files.
    child_bom_paths = (
        [Path(RESOURCES_DIR, "child_bom_1.json"), Path(RESOURCES_DIR, "child_bom_2.json")] if child_boms else None
    )
    result_bom_refs = sorted(
        res["bom-ref"]
        for res in get_dep_components(root_bom_path=root_bom_path, child_bom_paths=child_bom_paths, recursive=recursive)
    )
    assert snapshot == result_bom_refs


def test_convert_components_to_artifacts(snapshot: dict[str, DependencyInfo]) -> None:
    """Test converting CycloneDX components using internal artifact representation."""
    # Path to the root bom.json.
    root_bom_path = Path(RESOURCES_DIR, "root_bom.json")

    # Disable repo finding to prevent remote calls during testing
    load_defaults(os.path.join(os.path.dirname(os.path.abspath(__file__)), "defaults.ini"))
    assert defaults.getboolean("repofinder.java", "find_repos") is False

    # Path to the sub-project bom.json files.
    child_bom_paths = [Path(RESOURCES_DIR, child) for child in ["child_bom_1.json", "child_bom_2.json"]]

    # Pass a root bom.json and two sub-project bom.json files in recursive mode.
    result = convert_components_to_artifacts(
        get_dep_components(root_bom_path=root_bom_path, child_bom_paths=child_bom_paths, recursive=True)
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
    result = get_deps_from_sbom(bom_path)
    assert snapshot == result


def test_multiple_versions(snapshot: dict[str, DependencyInfo]) -> None:
    """Test converting CycloneDX components when there are multiple artifacts.

    Based on semantic versioning, version strings can contain alphabet characters.
    """
    # Path to the BOM file.
    bom_path = Path(RESOURCES_DIR, "bom_multi_versions.json")
    result = get_deps_from_sbom(bom_path)
    assert snapshot == result


def test_custom_sbom_name_with_maven() -> None:
    """Test reading cyclonedx maven sbom that was created using a custom name."""
    cyclonedx: CycloneDxMaven = CycloneDxMaven(
        "", "bom.json", "", defaults.get("dependency.resolver", "dep_tool_maven"), ""
    )
    custom_bom_dir = RESOURCES_DIR.joinpath("sbom_name_tests")
    assert cyclonedx.collect_dependencies(str(custom_bom_dir.joinpath("single_named_sbom")))
    assert cyclonedx.collect_dependencies(str(custom_bom_dir.joinpath("single_named_sbom_with_children")))
    assert not cyclonedx.collect_dependencies(str(custom_bom_dir.joinpath("single_named_sbom_with_multiple_children")))
    assert not cyclonedx.collect_dependencies(str(custom_bom_dir.joinpath("multiple_named_sboms")))
