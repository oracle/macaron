# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This DatabaseManager module handles the sqlite database connection."""
import logging
from types import TracebackType
from typing import Optional

from sqlalchemy import Column, ForeignKey, Table, create_engine, insert, select
from sqlalchemy.orm import Session, declarative_base, declarative_mixin, declared_attr
from sqlalchemy.sql.sqltypes import Boolean, Integer

from macaron.database.views import create_view

logger: logging.Logger = logging.getLogger(__name__)

ORMBase = declarative_base()


class DatabaseManager:
    """This class handles and manages the connection to sqlite database during the search session."""

    def __init__(self, db_path: str):
        """Initialize instance.

        Parameters
        ----------
        db_path : str
            The path to the target database.
        """
        self.engine = create_engine(f"sqlite+pysqlite:///{db_path}", echo=True, future=True)
        self.db_name = db_path
        self.session = Session(self.engine)

        ORMBase.metadata.create_all(self.engine)

    def terminate(self) -> None:
        """Terminate the connection to the sqlite database."""
        self.session.close()

    def __enter__(self) -> "DatabaseManager":
        return self

    def __exit__(
        self, exc_type: Optional[type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]
    ) -> None:
        self.session.commit()
        self.session.close()

    def add_and_commit(self, item) -> None:  # type: ignore
        """Add an ORM object to the session and commit it."""
        self.session.add(item)
        self.session.commit()

    def insert(self, table: Table, values: dict) -> None:
        """Add an ORM object to the session and commit it."""
        self.execute(insert(table).values(**values))

    def execute(self, query) -> None:  # type: ignore
        """Execute a sqlalchemy core api query."""
        with self.engine.connect() as conn:
            conn.execute(query)
            conn.commit()

    def create_tables(self) -> None:
        """
        Automatically create views for all tables known to _base.metadata.

        (declared using both core and declarative) which begin with an underscore.
        """
        for table_name, table in ORMBase.metadata.tables.items():
            if table_name[0] == "_":
                create_view(table_name[1:], ORMBase.metadata, select([table]))

        ORMBase.metadata.create_all(self.engine, checkfirst=True)


@declarative_mixin
class CheckResultTable:
    """
    Declarative mixin for check results.

    All tables for check results must inherit this class, these fields are automatically filled in by the analyzer.
    """

    @declared_attr  # type: ignore
    def id(self) -> Column:  # noqa: A003 # pylint: disable=invalid-name
        """Check result id."""
        return Column(Integer, primary_key=True, autoincrement=True)

    @declared_attr  # type: ignore
    def repository_id(self) -> Column:
        """Store the id of the repository to which the analysis pertains."""
        return Column(Integer, ForeignKey("_repository.id"), nullable=False)

    @declared_attr  # type: ignore
    def passed(self) -> Column:
        """Whether the check passed (whether or not it was skipped)."""
        return Column(Boolean, nullable=False)

    @declared_attr  # type: ignore
    def skipped(self) -> Column:
        """Whether the check was skipped."""
        return Column(Boolean, nullable=False)

    def columns(self):  # type: ignore
        """Return the list of columns in this table."""
        return self.metadata.tables[self.__tablename__].columns.keys()  # type: ignore # pylint: disable=no-member
