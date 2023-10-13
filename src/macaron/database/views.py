# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
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
from sqlalchemy.sql import Select, TableClause, table


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
    """View exists."""
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
    """Not view exists."""
    return not view_exists(ddl, target, bind, **kw)


def create_view(name: str, metadata: MetaData, selectable: Select[Any]) -> TableClause:
    """Create a view."""
    view = table(name)
    view._columns._populate_separate_keys(col._make_proxy(view) for col in selectable.selected_columns)

    sqlalchemy.event.listen(
        metadata,
        "after_create",
        CreateView(name, selectable).execute_if(callable_=view_doesnt_exist),
    )
    sqlalchemy.event.listen(metadata, "before_drop", DropView(name).execute_if(callable_=view_exists))
    return view
