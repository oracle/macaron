# Copyright (c) 2022 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module test DatabaseManager."""

import os
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy import Column
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.sql.sqltypes import Integer, String

from macaron.database.database_manager import DatabaseManager
from macaron.errors import MacaronError


class Base(DeclarativeBase):
    """Declarative base class for mapper."""


class ORMMappedTable(Base):
    """Check justification table for build_as_code."""

    __tablename__ = "_test_orm_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    value = Column(String)


DB_PATH = str(Path(__file__).parent.joinpath("macaron.db"))


@pytest.fixture()
def db_man() -> Iterable:
    """Set up the database and ensure it is empty."""
    db_manager = DatabaseManager(DB_PATH, base=Base)
    con = sqlite3.connect(DB_PATH)
    with closing(con), con:
        con.execute("drop table if exists _test_orm_table;")
        con.execute("drop view if exists test_orm_table;")
        con.commit()

    yield db_manager
    db_manager.engine.dispose()
    os.remove(DB_PATH)


def test_existing_schema_must_not_silently_drop_new_evidence(tmp_path: Path) -> None:
    """An old table must fail before create_all reuses it or writes incompatible facts."""
    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            "CREATE TABLE _test_orm_table (id INTEGER PRIMARY KEY);"
            "CREATE VIEW test_orm_table AS SELECT id FROM _test_orm_table;"
        )
    manager = DatabaseManager(str(path), base=Base)
    try:
        with pytest.raises(MacaronError, match="fresh output directory"):
            manager.create_tables()
        with closing(sqlite3.connect(path)) as connection:
            assert [row[1] for row in connection.execute("PRAGMA table_info(_test_orm_table)")] == ["id"]
    finally:
        manager.engine.dispose()


def test_existing_view_must_expose_current_columns(tmp_path: Path) -> None:
    """A compatible physical table cannot hide an outdated generated view."""

    class ViewBase(DeclarativeBase):
        """Isolated metadata models a fresh process before any views have been registered."""

    class ViewTable(ViewBase):
        """The current table includes evidence the old view does not expose."""

        __tablename__ = "_view_compatibility"
        id = Column(Integer, primary_key=True)
        evidence = Column(String)

    path = tmp_path / "view.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            "CREATE TABLE _view_compatibility (id INTEGER PRIMARY KEY, evidence TEXT);"
            "CREATE VIEW view_compatibility AS SELECT id FROM _view_compatibility;"
        )
    manager = DatabaseManager(str(path), base=ViewTable)
    try:
        with pytest.raises(MacaronError, match="fresh output directory"):
            manager.create_tables()
    finally:
        manager.engine.dispose()


@pytest.mark.parametrize(
    ("identifier", "test_value", "expect"),
    [
        (1, "Hello World", True),
        (2, "Hello World", False),
    ],
)
def test_orm_mapping(
    db_man: DatabaseManager,  # pylint: disable=redefined-outer-name
    identifier: int,
    test_value: str,
    expect: bool,
) -> None:
    """Create a table and add rows."""
    db_man.create_tables()
    with Session(db_man.engine) as db_session, db_session.begin():
        row = ORMMappedTable(value=test_value)
        db_session.add(row)

    query = "select * from _test_orm_table;"
    con = sqlite3.connect(DB_PATH)
    with closing(con), con:
        cursor = con.execute(query)
        rows = cursor.fetchall()
        assert (str(rows) == str([(identifier, test_value)])) == expect
