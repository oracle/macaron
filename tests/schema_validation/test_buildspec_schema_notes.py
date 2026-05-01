# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for keeping BuildSpec schema notes aligned with the JSON schema."""

import json
import os

import jsonschema

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
BUILDSPEC_SCHEMA = os.path.join(
    REPO_ROOT,
    "src",
    "macaron",
    "resources",
    "schemas",
    "macaron_buildspec_schema.json",
)
BUILDSPEC_SCHEMA_NOTES = os.path.join(
    REPO_ROOT,
    "src",
    "macaron",
    "resources",
    "schemas",
    "macaron_buildspec_schema.md",
)
PYPI_TOGA_BUILDSPEC = os.path.join(
    REPO_ROOT,
    "tests",
    "integration",
    "cases",
    "pypi_toga",
    "expected_default.buildspec",
)
HUGEGRAPH_COMPUTER_K8S_BUILDSPEC = os.path.join(
    REPO_ROOT,
    "tests",
    "integration",
    "cases",
    "org_apache_hugegraph",
    "computer-k8s",
    "expected_default.buildspec",
)


def test_buildspec_fixtures_match_schema() -> None:
    """Use integration fixtures as concrete schema-conforming BuildSpec examples."""
    with open(BUILDSPEC_SCHEMA, encoding="utf-8") as file:
        schema = json.load(file)

    for fixture in (PYPI_TOGA_BUILDSPEC, HUGEGRAPH_COMPUTER_K8S_BUILDSPEC):
        with open(fixture, encoding="utf-8") as file:
            buildspec = json.load(file)
        jsonschema.validate(schema=schema, instance=buildspec)


def test_buildspec_schema_notes_document_schema_fields() -> None:
    """Make sure the Markdown companion documents every schema field by name."""
    with open(BUILDSPEC_SCHEMA, encoding="utf-8") as file:
        schema = json.load(file)
    with open(BUILDSPEC_SCHEMA_NOTES, encoding="utf-8") as file:
        notes = file.read()

    missing_top_level_fields = [
        field for field in schema["properties"] if f"`{field}`" not in notes
    ]
    assert not missing_top_level_fields

    build_command_fields = schema["properties"]["build_commands"]["items"]["properties"]
    missing_build_command_fields = [
        field for field in build_command_fields if f"`{field}`" not in notes
    ]
    assert not missing_build_command_fields


def test_buildspec_schema_notes_cover_pypi_toga_fixture_fields() -> None:
    """Keep the notes grounded in the PyPI fixture validated by the integration test."""
    with open(PYPI_TOGA_BUILDSPEC, encoding="utf-8") as file:
        buildspec = json.load(file)
    with open(BUILDSPEC_SCHEMA_NOTES, encoding="utf-8") as file:
        notes = file.read()

    for field in buildspec:
        assert f"`{field}`" in notes

    for field in buildspec["build_commands"][0]:
        assert f"`{field}`" in notes

    assert "tests/integration/cases/pypi_toga/test.yaml" in notes
    assert "python -m build" in notes


def test_buildspec_schema_notes_cover_hugegraph_computer_k8s_fixture_fields() -> None:
    """Keep the notes grounded in the Maven fixture validated by the integration test."""
    with open(HUGEGRAPH_COMPUTER_K8S_BUILDSPEC, encoding="utf-8") as file:
        buildspec = json.load(file)
    with open(BUILDSPEC_SCHEMA_NOTES, encoding="utf-8") as file:
        notes = file.read()

    for field in buildspec:
        assert f"`{field}`" in notes

    for field in buildspec["build_commands"][0]:
        assert f"`{field}`" in notes

    assert "tests/integration/cases/org_apache_hugegraph/computer-k8s/test.yaml" in notes
    assert "pkg:maven/org.apache.hugegraph/computer-k8s@1.0.0" in notes
    assert "computer-k8s/pom.xml" in notes
