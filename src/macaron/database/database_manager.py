# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This DatabaseManager module handles the sqlite database connection."""

import logging
import sqlite3

logger: logging.Logger = logging.getLogger(__name__)


class DatabaseManager:
    """This class handles and manages the connection to sqlite database during the search session.

    Parameters
    ----------
    db_path : str
        The path to the target database.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.is_init = False
        self.db_con = None
        self.db_cursor = None

    def init_conn(self) -> None:
        """Initiate the connection to the target database."""
        logger.debug("Connecting to database at %s", self.db_path)
        self.db_con = sqlite3.connect(self.db_path)  # type: ignore[assignment]
        self.db_cursor = self.db_con.cursor()  # type: ignore[attr-defined]
        self.is_init = True

    def execute_query(self, query: str, commit: bool = True) -> None:
        """Execute a single query against the sqlite database and commit it.

        Parameters
        ----------
        query : str
            The SQLite query to perform.
        commit : bool
            If True, the result of this query is committed to the database.
        """
        logger.debug("Executing DB query: %s", query)
        self.db_cursor.execute(query)  # type: ignore[attr-defined]
        if commit:
            self.db_con.commit()  # type: ignore[attr-defined]

    def execute_multi_queries(self, queries: list, commit: bool = True) -> None:
        """Execute multiple queries and ignore sqlite3.Operational Errors.

        Parameters
        ----------
        queries : list
            The list of queries to perform.
        commit : bool
            If True, the result of this query is committed to the database.
        """
        logger.debug("Executing multiple queries")
        for query in queries:
            try:
                self.execute_query(query, commit)
            except sqlite3.OperationalError as error:
                logger.debug("Sqlite3.OperationalError: %s. Continue", error)

    def execute_select_query(self, query: str) -> list:
        """Execute the select query and return the list of results.

        Parameters
        ----------
        query : str
            The SELECT query to execute.

        Returns
        -------
        list
        """
        logger.debug("Executing DB query: %s", query)
        try:
            result = self.db_cursor.execute(query).fetchall()  # type: ignore
            return result
        except sqlite3.OperationalError as error:
            logger.error(
                "Sqlite3.OperationalError while performing SELECT query: %s. Continue",
                error,
            )
            return []

    def execute_insert_query(self, placeholder_query: str, data: dict) -> None:
        """Execute the insert query using the named style query from sqlite3.

        Parameters
        ----------
        placeholder_query : str
            The named style INSERT query.
        data : str
            The data dictionary to be inserted into the final query.
        """
        logger.debug("Executing insert query on data %s", data)
        try:
            self.db_cursor.execute(placeholder_query, data)  # type: ignore
            self.db_con.commit()  # type: ignore
        except sqlite3.OperationalError as error:
            logger.error(
                "Sqlite3.OperationalError while performing INSERT query: %s. Continue",
                error,
            )

    def terminate(self) -> None:
        """Terminate the connection to the sqlite database."""
        self.db_con.close()  # type: ignore
