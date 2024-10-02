# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This DatabaseManager module handles the sqlite database connection."""
import collections.abc
import functools
import logging
import os
import typing

import sqlalchemy.exc
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.database.views import create_view

logger: logging.Logger = logging.getLogger(__name__)


class ORMBase(DeclarativeBase):
    """ORM base class.

    To prevent Sphinx from rendering the docstrings in `DeclarativeBase`, make
    this docstring private:

    :meta private:
    """


class DatabaseManager:
    """This class handles and manages the connection to sqlite database during the session."""

    def __init__(self, db_path: str, base: type[DeclarativeBase] = ORMBase):
        """Initialize instance.

        Parameters
        ----------
        db_path : str
            The path to the target database.
        """
        self.engine = create_engine(f"sqlite+pysqlite:///{db_path}", echo=False)
        self.db_name = db_path
        self._base = base

    def create_tables(self) -> None:
        """
        Automatically create views for all tables known to _base.metadata.

        Creates all explicitly declared tables, and creates views proxying all tables beginning with an underscore.

        Note: this is specifically to allow the tables to be loaded into souffle:
            https://souffle-lang.github.io/directives#input-directive
        """
        try:
            self._base.metadata.create_all(self.engine, checkfirst=True)
            for table_name, table in self._base.metadata.tables.items():
                if table_name[0] == "_":
                    create_view(table_name[1:], self._base.metadata, select(table))
            self._base.metadata.create_all(self.engine, checkfirst=True)
        except sqlalchemy.exc.SQLAlchemyError as error:
            logger.error("Database error on create tables %s", error)


_T = typing.TypeVar("_T")
_P = typing.ParamSpec("_P")


class cache_return(typing.Generic[_T, _P]):  # pylint: disable=invalid-name # noqa: N801
    """The decorator to create a singleton DB session."""

    def __init__(self, function: collections.abc.Callable[_P, _T]) -> None:
        functools.update_wrapper(self, function)
        self.function = function

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> _T:
        """Store or get the cached function return value."""
        try:
            return self.return_value
        except AttributeError:
            self.return_value: _T = self.function(*args, **kwargs)  # pylint: disable=attribute-defined-outside-init
            return self.return_value

    def clear(self) -> None:
        """Remove the cached return value."""
        try:
            delattr(self, "return_value")
        except AttributeError:
            logger.debug("No cached return value to remove.")


@cache_return
def get_db_manager() -> DatabaseManager:
    """
    Get the database manager singleton object.

    Returns
    -------
    DatabaseManager
        The database manager singleton object.
    """
    db_path = os.path.join(global_config.output_path, defaults.get("database", "db_name", fallback="macaron.db"))
    db_man = DatabaseManager(db_path)
    return db_man


@cache_return
def get_db_session(session: Session | None = None) -> Session:
    """Get the current database session as a singleton object.

    This function expects to receive the Session object on the first
    call to cache it. The subsequent calls do not need to pass the
    Session object unless `get_db_session.clear()` is called.

    Parameters
    ----------
    Session | None
        The session object to be cached.

    Returns
    -------
    Session
        The current database session as a singleton object.

    Raises
    ------
    RuntimeError
        Happens if a database session is not created.
    """
    if session is None:
        raise RuntimeError("Failed to create a database session.")
    return session
