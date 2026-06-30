# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the POM parser."""

import os
from pathlib import Path

import pytest

from macaron.parsers.pomparser import (
    extract_included_pom_modules,
    find_matching_maven_module_build_configs,
)
from macaron.parsers.pomparser import parse_pom_string as parse

RESOURCES_DIR = Path(__file__).parent.joinpath("resources")


def test_pomparser_parse() -> None:
    """Test parsing a valid XML file."""
    with open(os.path.join(RESOURCES_DIR, "valid.xml"), encoding="utf8") as file:
        assert parse(file.read())


@pytest.mark.parametrize(
    "file_name",
    [
        "forbidden_entity.xml",
        "invalid.xml",
    ],
)
def test_pomparser_parse_invalid(file_name: str) -> None:
    """Test parsing invalid XML files."""
    with open(os.path.join(RESOURCES_DIR, file_name), encoding="utf8") as file:
        assert not parse(file.read())


def test_extract_included_pom_modules(tmp_path: Path) -> None:
    """Test extracting module entries from a parent pom.xml."""
    parent_pom = tmp_path.joinpath("pom.xml")
    parent_pom.write_text(
        "\n".join(
            [
                "<project>",
                "  <modules>",
                "    <module>core</module>",
                "    <module>feature/api</module>",
                "  </modules>",
                "</project>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert extract_included_pom_modules(parent_pom) == ["core", "feature/api"]


def test_find_matching_maven_module_build_configs(tmp_path: Path) -> None:
    """Test finding module pom.xml files from artifact id suffix matching."""
    repo_path = tmp_path.joinpath("repo")
    parent_pom = repo_path.joinpath("pom.xml")
    repo_path.joinpath("core").mkdir(parents=True)
    repo_path.joinpath("test-junit5").mkdir(parents=True)
    repo_path.joinpath("core", "pom.xml").write_text("<project />\n", encoding="utf-8")
    target_pom = repo_path.joinpath("test-junit5", "pom.xml")
    target_pom.write_text("<project />\n", encoding="utf-8")
    parent_pom.write_text(
        "\n".join(
            [
                "<project>",
                "  <modules>",
                "    <module>core</module>",
                "    <module>test-junit5</module>",
                "  </modules>",
                "</project>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert find_matching_maven_module_build_configs(repo_path, "micronaut-test-junit5") == [target_pom]
