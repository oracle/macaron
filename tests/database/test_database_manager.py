# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module test DatabaseManager
"""

import sqlite3
from pathlib import Path
from unittest import TestCase

from sqlalchemy import Column, Table
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.sqltypes import Integer, String

from macaron.database.database_manager import DatabaseManager


class Base(DeclarativeBase):
    """Declarative base class for mapper."""


class ORMMappedTable(Base):
    """Check justification table for build_as_code."""

    __tablename__ = "_test_orm_table"

    id = Column(Integer, primary_key=True, autoincrement=True)  # noqa: A003 pylint # ignore=invalid-name
    value = Column(String)


class TestDatabaseManager(TestCase):
    """
    Test the DatabaseManager module.
    """

    TEST_VALUE = "Hello World"
    TEST_IDENT = 10

    def setUp(self) -> None:
        """Set up the database and ensure it is empty."""
        self.db_path = str(Path(__file__).parent.joinpath("macaron.db"))
        self.db_man = DatabaseManager(self.db_path, base=Base)
        con = sqlite3.connect(self.db_path)
        with con:
            con.execute("drop table if exists test_table;")
            con.execute("drop table if exists new_test_table;")
            con.execute("drop table if exists _test_table;")
            con.execute("drop table if exists _test_orm_table;")
            con.execute("drop view if exists test_orm_table;")
            con.commit()

    @staticmethod
    def _assert_query_result(db_path: str, query: str, expect: list[tuple]) -> None:
        con = sqlite3.connect(db_path)
        with con:
            cursor = con.execute(query)
            rows = cursor.fetchall()
            assert str(rows) == str(expect)

    def test_insert(self) -> None:
        """Insert to database using core api."""
        tbl = Table("test_table", Base.metadata, Column("test", String))
        self.db_man.create_tables()
        self.db_man.insert(tbl, {"test": self.TEST_VALUE})
        self._assert_query_result(self.db_path, "select * from test_table;", [(self.TEST_VALUE,)])

    def test_context_manager_orm(self) -> None:
        """Connect to database using context manager and create tables, with concurrent connections."""
        with DatabaseManager(self.db_path, base=Base) as db_man:
            table = ORMMappedTable(id=10, value=self.TEST_VALUE)
            db_man.create_tables()
            db_man.add_and_commit(table)
            db_man.session.flush()

        self._assert_query_result(self.db_path, "select * from _test_orm_table;", [(self.TEST_IDENT, self.TEST_VALUE)])
        self._assert_query_result(self.db_path, "select * from test_orm_table;", [(self.TEST_IDENT, self.TEST_VALUE)])

        # Interacting with db manager after ended session should not crash
        db_man.add_and_commit(ORMMappedTable(id=100, value=self.TEST_VALUE))
        tbl = Table("new_test_table", Base.metadata, Column("test", String))
        db_man.create_tables()
        db_man.insert(tbl, {"test": self.TEST_VALUE})
        self._assert_query_result(self.db_path, "select * from new_test_table;", [(self.TEST_VALUE,)])

    def tearDown(self) -> None:
        """Terminate the database connection."""
        self.db_man.terminate()
