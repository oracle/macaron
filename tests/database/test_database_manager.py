# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module test DatabaseManager.
"""

import os
import sqlite3
from collections.abc import Iterable
from pathlib import Path

import pytest
from sqlalchemy import Column
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.sql.sqltypes import Integer, String

from macaron.database.database_manager import DatabaseManager


class Base(DeclarativeBase):
    """Declarative base class for mapper."""


class ORMMappedTable(Base):
    """Check justification table for build_as_code."""

    __tablename__ = "_test_orm_table"

    id = Column(Integer, primary_key=True, autoincrement=True)  # noqa: A003 pylint # ignore=invalid-name
    value = Column(String)


DB_PATH = str(Path(__file__).parent.joinpath("macaron.db"))


@pytest.fixture()
def db_man() -> Iterable:
    """Set up the database and ensure it is empty."""
    db_manager = DatabaseManager(DB_PATH, base=Base)
    con = sqlite3.connect(DB_PATH)
    with con:
        con.execute("drop table if exists _test_orm_table;")
        con.execute("drop view if exists test_orm_table;")
        con.commit()
    yield db_manager
    os.remove(DB_PATH)


@pytest.mark.parametrize(
    ("identifier", "test_value", "expect"),
    [
        (1, "Hello World", True),
        (2, "Hello World", False),
    ],
)
def test_orm_mapping(
    db_man: DatabaseManager, identifier: int, test_value: str, expect: bool  # pylint: disable=redefined-outer-name
) -> None:
    """Create a table and add rows."""
    db_man.create_tables()
    with Session(db_man.engine) as db_session, db_session.begin():
        row = ORMMappedTable(value=test_value)
        db_session.add(row)

    query = "select * from _test_orm_table;"
    con = sqlite3.connect(DB_PATH)
    with con:
        cursor = con.execute(query)
        rows = cursor.fetchall()
        assert (str(rows) == str([(identifier, test_value)])) == expect
