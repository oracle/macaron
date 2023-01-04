# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
SQLAlchemy View creation.

https://github.com/sqlalchemy/sqlalchemy/wiki/Views
"""

import sqlalchemy as sa
from sqlalchemy.ext import compiler
from sqlalchemy.schema import DDLElement
from sqlalchemy.sql import TableClause, table


class CreateView(DDLElement):
    """CreateView."""

    def __init__(self, name, selectable):  # type: ignore
        self.name = name
        self.selectable = selectable


class DropView(DDLElement):
    """DropView."""

    def __init__(self, name):  # type: ignore
        self.name = name


@compiler.compiles(CreateView)
def _create_view(element, compiler, **kw):  # type: ignore
    return "CREATE VIEW {} AS {}".format(
        element.name,
        compiler.sql_compiler.process(element.selectable, literal_binds=True),
    )


@compiler.compiles(DropView)
def _drop_view(element, compiler, **kw):  # type: ignore
    return "DROP VIEW %s" % (element.name)


def view_exists(ddl, target, connection, **kw):  # type: ignore
    """View exists."""
    return ddl.name in sa.inspect(connection).get_view_names()


def view_doesnt_exist(ddl, target, connection, **kw):  # type: ignore
    """Not view exists."""
    return not view_exists(ddl, target, connection, **kw)  # type: ignore


def create_view(name, metadata, selectable) -> TableClause:  # type: ignore
    """Create a view."""
    view = table(name)
    view._columns._populate_separate_keys(col._make_proxy(view) for col in selectable.selected_columns)

    sa.event.listen(
        metadata,
        "after_create",
        CreateView(name, selectable).execute_if(callable_=view_doesnt_exist),  # type: ignore
    )
    sa.event.listen(metadata, "before_drop", DropView(name).execute_if(callable_=view_exists))  # type: ignore
    return view
