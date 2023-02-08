# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This DatabaseManager module handles the sqlite database connection."""
import logging
from types import TracebackType
from typing import Any, Optional

import sqlalchemy.exc
from sqlalchemy import Table, create_engine, insert, select
from sqlalchemy.orm import Session, declarative_base

from macaron.database.views import create_view

logger: logging.Logger = logging.getLogger(__name__)

ORMBase = declarative_base()


class DatabaseManager:
    """
    This class handles and manages the connection to sqlite database during the session.

    Note that since SQLAlchemy lazy-loads the fields of mapped ORM objects, if the database connection is closed any
    orm-mapped objects will become invalid. As such the lifetime of the database manager must be longer than any of the
    objects added to the database (using add() or add_and_commit()).
    """

    def __init__(self, db_path: str, base=ORMBase):  # type: ignore
        """Initialize instance.

        Parameters
        ----------
        db_path : str
            The path to the target database.
        """
        self.engine = create_engine(f"sqlite+pysqlite:///{db_path}", echo=False, future=True)
        self.db_name = db_path
        self.session = Session(self.engine)
        self._base = base

    def terminate(self) -> None:
        """Terminate the connection to the database, discarding any transaction in progress."""
        self.session.close()

    def __enter__(self) -> "DatabaseManager":
        return self

    def __exit__(
        self, exc_type: Optional[type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]
    ) -> None:
        self.terminate()

    def add_and_commit(self, item) -> None:  # type: ignore
        """Add an ORM object to the session and commit it.

        Following commit any auto-updated primary key values in the object will be populated and readable.
        The object can still be modified and read after being committed.

        Parameters
        ----------
        item: the orm-mapped object to add to the database.
        """
        try:
            self.session.add(item)
            self.session.commit()
        except sqlalchemy.exc.SQLAlchemyError as error:
            logger.error("Database error %s", error)
            self.session.rollback()

    def add(self, item) -> None:  # type: ignore
        """Add an item to the database and flush it.

        Once added the row remains accessible and modifiable, and the primary key field is populated to reflect its
        record in the database.

        If terminate is called before commit the object will be lost.

        Parameters
        ----------
        item:
            the orm-mapped object to add to the database.
        """
        try:
            self.session.add(item)
            self.session.flush()
        except sqlalchemy.exc.SQLAlchemyError as error:
            logger.error("Database error %s", error)
            self.session.rollback()

    def insert(self, table: Table, values: dict) -> None:
        """Populate the table with provided values and add it to the database using the core api.

        Parameters
        ----------
        table: Table
            The Table to insert to
        values: dict
            The mapping from column names to values to insert into the Table
        """
        try:
            self.execute(insert(table).values(**values))
        except sqlalchemy.exc.SQLAlchemyError as error:
            logger.error("Database error %s", error)

    def execute(self, query: Any) -> None:
        """
        Execute a SQLAlchemy core api query using a short-lived engine connection.

        Parameters
        ----------
        query: Any
            The SQLalchemy query to execute
        """
        with self.engine.connect() as conn:
            conn.execute(query)
            conn.commit()
        self.session.commit()

    def create_tables(self) -> None:
        """
        Automatically create views for all tables known to _base.metadata.

        Creates all explicitly declared tables, and creates views proxying all tables beginning with an underscore.

        Note: this is specifically to allow the tables to be loaded into souffle:
            https://souffle-lang.github.io/directives#input-directive
        """
        try:
            for table_name, table in self._base.metadata.tables.items():
                if table_name[0] == "_":
                    create_view(table_name[1:], self._base.metadata, select(table))

            self._base.metadata.create_all(self.engine, checkfirst=True)
        except sqlalchemy.exc.SQLAlchemyError as error:
            logger.error("Database error on create tables %s", error)
