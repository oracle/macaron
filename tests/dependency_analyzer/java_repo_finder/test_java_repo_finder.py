# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the repo finder.
"""
import os
from pathlib import Path

import pytest
import sqlalchemy

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.database.database_manager import DatabaseManager
from macaron.database.table_definitions import RepositoryTable
from macaron.dependency_analyzer.java_repo_finder import create_urls, find_parent, find_scm, parse_pom


def test_java_repo_finder() -> None:
    """Test the functions of the repo finder."""
    repositories = defaults.get_list(
        "repofinder.java", "artifact_repositories", fallback=["https://repo.maven.apache.org/maven2"]
    )
    group = "group"
    artifact = "artifact"
    version = "version"
    created_urls = create_urls(group, artifact, version, repositories)
    assert created_urls

    resources_dir = Path(__file__).parent.joinpath("resources")
    with open(os.path.join(resources_dir, "example_pom.xml"), encoding="utf8") as file:
        file_data = file.read()
        pom = parse_pom(file_data)
        assert pom is not None
        found_urls, count = find_scm(pom, ["scm.url", "scm.connection", "scm.developerConnection"])
        assert count == 3
        expected = [
            "https://github.com/owner/project",
            "ssh://git@hostname:port/owner/project.git",
            "git@github.com:owner/project.git",
        ]
        assert expected == list(found_urls)


def test_java_repo_finder_hierarchical() -> None:
    """Test the hierarchical capabilities of the repo finder."""
    resources_dir = Path(__file__).parent.joinpath("resources")
    with open(os.path.join(resources_dir, "example_pom_no_scm.xml"), encoding="utf8") as file:
        file_data = file.read()
        pom = parse_pom(file_data)
        assert pom is not None
        group, artifact, version = find_parent(pom)
        assert group == "owner"
        assert artifact == "parent"
        assert version == "1"


@pytest.fixture()
def database_fixture() -> DatabaseManager:  # type: ignore
    """Set up and tear down a test database."""
    database_path = os.path.join(global_config.output_path, "test.db")
    db_man = DatabaseManager(database_path)
    db_man.create_tables()
    yield db_man
    db_man.terminate()
    os.remove(database_path)


def test_java_repo_database(database_fixture: DatabaseManager) -> None:  # pylint: disable=redefined-outer-name
    """Test the database functionality used by the repo finder."""
    data = {
        "full_name": "test_repo",
        "commit_date": "02/02/02",
        "branch_name": "branch_1",
        "commit_sha": "shashasha",
        "remote_path": "remote_path",
        "namespace": "namespace",
        "name": "name",
    }
    table = RepositoryTable(**data)
    database_fixture.add(table)
    database_fixture.session.commit()
    query = sqlalchemy.select(RepositoryTable).where(
        RepositoryTable.namespace == "namespace", RepositoryTable.name == "name"
    )
    result = database_fixture.execute_and_return(query)
    row = result.first()
    assert row is not None
    assert row.remote_path == "remote_path"
