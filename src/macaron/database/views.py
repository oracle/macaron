# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# pylint: skip-file

"""
SQLAlchemy View creation.

https://github.com/sqlalchemy/sqlalchemy/wiki/Views
"""

from typing import Any

import sqlalchemy as sa
import sqlalchemy.event
from sqlalchemy import Connection
from sqlalchemy.ext import compiler
from sqlalchemy.schema import BaseDDLElement, DDLElement, MetaData, SchemaItem, Table
from sqlalchemy.sql import Select


class CreateView(DDLElement):
    """CreateView."""

    def __init__(self, name: str, selectable: Select[Any]):
        self.name = name
        self.selectable = selectable


class DropView(DDLElement):
    """DropView."""

    def __init__(self, name: str):
        self.name = name


@compiler.compiles(CreateView)  # type: ignore
def _create_view(element, comp, **kw):
    return f"CREATE VIEW {element.name} AS {comp.sql_compiler.process(element.selectable, literal_binds=True)}"


@compiler.compiles(DropView)  # type: ignore
def _drop_view(element, comp, **kw):
    return "DROP VIEW %s" % (element.name)


def view_exists(
    ddl: BaseDDLElement,
    target: SchemaItem,
    bind: Connection | None,
    tables: list[Table] | None = None,
    state: Any | None = None,
    **kw: Any,
) -> bool:
    """Check if a view exists in the database.

    This function checks whether a view, defined by the `CreateView` or `DropView`
    object, already exists in the database. It relies on the provided `bind` connection
    to inspect the existing views in the database.

    Parameters
    ----------
    ddl : BaseDDLElement
        The DDL element that represents the creation or dropping of a view.
    target : SchemaItem
        The target schema item (not directly used in this check).
    bind : Connection | None
        The database connection used to inspect the database for existing views.
    tables : list[Table] | None, optional
        A list of tables (not directly used in this check).
    state : Any | None, optional
        The state of the object (not directly used in this check).
    kw : Any
        Additional keyword arguments passed to the function (not directly used).

    Returns
    -------
    bool
        Returns `True` if the view exists in the database, `False` otherwise.
    """
    if isinstance(ddl, CreateView) or isinstance(ddl, DropView):
        assert isinstance(bind, Connection)
        return ddl.name in sa.inspect(bind).get_view_names()
    return False


def view_doesnt_exist(
    ddl: BaseDDLElement,
    target: SchemaItem,
    bind: Connection | None,
    tables: list[Table] | None = None,
    state: Any | None = None,
    **kw: Any,
) -> bool:
    """Check if a view does not exist in the database.

    This function is the inverse of `view_exists`. It returns `True` if the view
    defined by the `CreateView` or `DropView` object does not exist in the database.

    Parameters
    ----------
    ddl : BaseDDLElement
        The DDL element that represents the creation or dropping of a view.
    target : SchemaItem
        The target schema item (not directly used in this check).
    bind : Connection | None
        The database connection used to inspect the database for existing views.
    tables : list[Table] | None, optional
        A list of tables (not directly used in this check).
    state : Any | None, optional
        The state of the object (not directly used in this check).
    kw : Any
        Additional keyword arguments passed to the function (not directly used).

    Returns
    -------
    bool
        Returns `True` if the view does not exist in the database, `False` otherwise.
    """
    return not view_exists(ddl, target, bind, **kw)


def create_view(name: str, metadata: MetaData, selectable: Select[Any]) -> None:
    """Create and manage a view for an existing table, including its lifecycle.

    This function allows you to define a SQL view based on an existing table, as well as
    handle operations like creation and deletion.

    For an example implementation, see this Wiki page:
    https://github.com/sqlalchemy/sqlalchemy/wiki/Views


    Parameters
    ----------
    name : str
        The name of the view to be created.
    metadata : MetaData
        The MetaData object that contains the schema and is used to listen for
        the `after_create` and `before_drop` events.
    selectable : Select[Any]
        A table that defines the content of the view.
    """
    # Create the view after all tables are created:.
    sqlalchemy.event.listen(
        metadata,
        "after_create",
        CreateView(name, selectable).execute_if(callable_=view_doesnt_exist),
    )

    # Ensure the view is dropped before any tables in the database are dropped.
    sqlalchemy.event.listen(metadata, "before_drop", DropView(name).execute_if(callable_=view_exists))
