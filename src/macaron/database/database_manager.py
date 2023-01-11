# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This DatabaseManager module handles the sqlite database connection."""
import logging
from types import TracebackType
from typing import Optional

import sqlalchemy.exc
from sqlalchemy import Table, create_engine, insert, select
from sqlalchemy.orm import Session, declarative_base

from macaron.database.views import create_view

logger: logging.Logger = logging.getLogger(__name__)

ORMBase = declarative_base()


class DatabaseManager:
    """This class handles and manages the connection to sqlite database during the search session."""

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
        """Add an ORM object to the session and commit it."""
        try:
            self.session.add(item)
            self.session.commit()
        except sqlalchemy.exc.SQLAlchemyError as error:
            logger.error("Database error %s", error)
            self.session.rollback()

    def insert(self, table: Table, values: dict) -> None:
        """Add a table row and commit it using the core api."""
        try:
            self.execute(insert(table).values(**values))
        except sqlalchemy.exc.SQLAlchemyError as error:
            logger.error("Database error %s", error)

    def execute(self, query) -> None:  # type: ignore
        """Execute a sqlalchemy core api query."""
        with self.engine.connect() as conn:
            conn.execute(query)
            conn.commit()
        self.session.commit()

    def create_tables(self) -> None:
        """
        Automatically create views for all tables known to _base.metadata.

        Creates all explicitly declared tables, and creates views proxying all tables beginning with an underscore.
        """
        try:
            for table_name, table in self._base.metadata.tables.items():
                if table_name[0] == "_":
                    create_view(table_name[1:], self._base.metadata, select([table]))

            self._base.metadata.create_all(self.engine, checkfirst=True)
        except sqlalchemy.exc.SQLAlchemyError as error:
            logger.error("Database error on create tables %s", error)
