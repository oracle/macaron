# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains tests for the macaron_db_extractor module."""

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

import pytest
from packageurl import PackageURL
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from macaron import __version__
from macaron.build_spec_generator.macaron_db_extractor import (
    QueryMacaronDatabaseError,
    Repository,
    lookup_any_build_command,
    lookup_build_tools_check,
    lookup_latest_component_id,
    lookup_repository,
)
from macaron.database.table_definitions import Analysis, CommitFinderInfo, Component, ORMBase, RepoFinderMetadata
from macaron.repo_finder.repo_finder import RepoFinderInfo

# pylint: disable=redefined-outer-name


@pytest.fixture()
def macaron_db_session() -> Generator[Session, Any, None]:
    """Return a session to a memory stored SQLite database with Macaron's database schema.

    The database is empty. This fixture's scope is function to prevent polluting between tests.
    It also handles closing the session after the test function finishes.
    """
    engine = create_engine("sqlite:///:memory:")
    ORMBase.metadata.create_all(engine)

    session_maker = sessionmaker(engine)
    session = session_maker()

    yield session

    session.close()


@pytest.fixture()
def invalid_db_session() -> Generator[Session, Any, None]:
    """Return a session to a memory stored SQLite database.

    This databaes doesn't have Macaron database schema, hence it considered invalid.
    """
    engine = create_engine("sqlite:///:memory:")

    session_maker = sessionmaker(engine)
    session = session_maker()

    yield session

    session.close()


@pytest.mark.parametrize(
    ("input_data", "query_purl_string", "expect_result"),
    [
        pytest.param(
            [],
            "pkg:maven/oracle/macaron@0.16.0",
            None,
            id="The database is empty.",
        ),
        pytest.param(
            [
                (
                    datetime(year=2025, month=5, day=6, hour=10, minute=30, second=30, tzinfo=timezone.utc),
                    "pkg:maven/boo/foo@0.2.0",
                ),
                (
                    datetime(year=2025, month=5, day=6, hour=10, minute=30, second=30, tzinfo=timezone.utc),
                    "pkg:maven/boo/boohoo@1.0",
                ),
            ],
            "pkg:maven/oracle/macaron@0.16.0",
            None,
            id="The database is not empty, but no component matches the query PackageURL string.",
        ),
        pytest.param(
            [
                (
                    datetime(year=2025, month=5, day=6, hour=10, minute=30, second=30, tzinfo=timezone.utc),
                    "pkg:maven/oracle/macaron@0.16.0",
                ),
                (
                    datetime(year=2025, month=5, day=6, hour=10, minute=30, second=30, tzinfo=timezone.utc),
                    "pkg:maven/boo/foo@0.1.0",
                ),
                (
                    datetime(year=2025, month=5, day=6, hour=10, minute=30, second=30, tzinfo=timezone.utc),
                    "pkg:maven/oracle/macaron@0.16.0",
                ),
            ],
            "pkg:maven/oracle/macaron@0.16.0",
            3,
            id="When two analyses of the same PURL has the same timestamp, the component id of the latest analysis is returned.",
        ),
    ],
)
def test_lookup_latest_component_id(
    macaron_db_session: Session,
    input_data: list[tuple[datetime, str]],
    query_purl_string: str,
    expect_result: int | None,
) -> None:
    """Test the lookup_latest_component_id function."""
    for utc_timestamp, purl_string in input_data:
        analysis = Analysis(
            analysis_time=utc_timestamp,
            macaron_version=__version__,
        )

        repo_finder_metadata = RepoFinderMetadata(
            repo_finder_outcome=RepoFinderInfo.NOT_USED,
            commit_finder_outcome=CommitFinderInfo.NOT_USED,
            found_url="",
            found_commit="",
        )

        _ = Component(
            purl=purl_string,
            analysis=analysis,
            repository=None,
            repo_finder_metadata=repo_finder_metadata,
        )

        macaron_db_session.add(analysis)

    macaron_db_session.commit()
    assert lookup_latest_component_id(PackageURL.from_string(query_purl_string), macaron_db_session) == expect_result


def test_lookup_repository_empty_db(macaron_db_session: Session) -> None:
    """Test the lookup_repository function."""
    assert not lookup_repository(1, macaron_db_session)


def test_lookup_repository(macaron_db_session: Session) -> None:
    """Test the lookup_repository function."""
    analysis = Analysis(
        analysis_time=datetime(year=2025, month=5, day=6, hour=10, minute=30, second=30, tzinfo=timezone.utc),
        macaron_version=__version__,
    )

    repository = Repository(
        full_name="oracle/macaron",
        complete_name="github.com/oracle/macaron",
        remote_path="https://github.com/oracle/macaron",
        branch_name="main",
        commit_sha="d2b95262091d6572cc12dcda57d89f9cd44ac88b",
        commit_date="2023-02-10T15:11:14+08:00",
        fs_path="/boo/foo/macaron",
        files=["boo.txt", "foo.xml"],
    )

    repo_finder_metadata_1 = RepoFinderMetadata(
        repo_finder_outcome=RepoFinderInfo.NOT_USED,
        commit_finder_outcome=CommitFinderInfo.NOT_USED,
        found_url="",
        found_commit="",
    )

    repo_finder_metadata_2 = RepoFinderMetadata(
        repo_finder_outcome=RepoFinderInfo.NOT_USED,
        commit_finder_outcome=CommitFinderInfo.NOT_USED,
        found_url="",
        found_commit="",
    )

    component_without_repo = Component(
        purl="pkg:maven/boo/foo@0.1.0",
        analysis=analysis,
        repository=None,
        repo_finder_metadata=repo_finder_metadata_1,
    )

    component_with_repo = Component(
        purl="pkg:maven/oracle/macaron@0.16.0",
        analysis=analysis,
        repository=repository,
        repo_finder_metadata=repo_finder_metadata_2,
    )

    macaron_db_session.add(analysis)
    macaron_db_session.commit()

    assert not lookup_repository(component_without_repo.id, macaron_db_session)
    lookup_repo = lookup_repository(component_with_repo.id, macaron_db_session)
    assert lookup_repo
    assert lookup_repo.remote_path == "https://github.com/oracle/macaron"
    assert lookup_repo.commit_sha == "d2b95262091d6572cc12dcda57d89f9cd44ac88b"


def test_lookup_any_build_command_empty_db(macaron_db_session: Session) -> None:
    """Test the lookup_any_build_command function with an empty database."""
    assert not lookup_any_build_command(component_id=1, session=macaron_db_session)


def test_invalid_input_databse(invalid_db_session: Session) -> None:
    """Test handling invalid input database."""
    with pytest.raises(QueryMacaronDatabaseError):
        lookup_any_build_command(
            component_id=1,
            session=invalid_db_session,
        )

    with pytest.raises(QueryMacaronDatabaseError):
        lookup_build_tools_check(
            component_id=1,
            session=invalid_db_session,
        )

    with pytest.raises(QueryMacaronDatabaseError):
        lookup_repository(
            component_id=1,
            session=invalid_db_session,
        )

    with pytest.raises(QueryMacaronDatabaseError):
        lookup_latest_component_id(
            purl=PackageURL.from_string("pkg:maven/oracle/macaron@0.16.0"),
            session=invalid_db_session,
        )
