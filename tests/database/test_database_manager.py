# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module test DatabaseManager
"""

import sqlite3
from pathlib import Path
from unittest import TestCase

from macaron.database.database_manager import DatabaseManager


class TestDatabaseManager(TestCase):
    """
    Test the DatabaseManager module.
    """

    def setUp(self) -> None:
        db_path = str(Path(__file__).parent.joinpath("macaron.db"))
        self.db_man = DatabaseManager(db_path)

    def tearDown(self) -> None:
        self.db_man.terminate()

    def test_init(self) -> None:
        """
        Test initializing the database connection.
        """
        assert not self.db_man.is_init
        self.db_man.init_conn()
        assert self.db_man.is_init

    def test_execute_query(self) -> None:
        """
        Test executing queries.
        """
        sample_query = """
            CREATE TABLE IF NOT EXISTS gh_repositories (
                repo_id INTEGER PRIMARY KEY,
                name TEXT
            )
        """
        invalid_query = """
            SELECT * FROM TABLE invalid_table
        """
        self.db_man.init_conn()
        self.db_man.execute_query(sample_query, commit=False)
        self.assertRaises(sqlite3.OperationalError, self.db_man.execute_query, invalid_query)

    def test_execute_multi_queries(self) -> None:
        """
        Test executing script method, cannot mock Connection and Cursor because they are builts-in
        """
        sample_queries = [
            """
            CREATE TABLE IF NOT EXISTS gh_repositories (
                repo_id INTEGER PRIMARY KEY
            );
            """,
            """
            INSERT INTO gh_repositories VALUES (
                2345
            );
            """,
        ]
        invalid_query = """
            SELECT * FROM TABLE invalid_table
        """
        self.db_man.init_conn()
        self.db_man.execute_multi_queries(sample_queries, commit=False)

        # Test for catching sqlite3.Operational errors
        self.db_man.execute_multi_queries([invalid_query])
