# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Generate souffle datalog for policy prelude."""

from sqlalchemy import Column, MetaData, Table
from sqlalchemy.sql.sqltypes import Boolean, Integer, String, Text

from macaron.database.database_manager import ORMBase


def column_to_souffle_type(column: Column) -> str:
    """Return a souffle type string for a SQLAlchemy Column."""
    sql_type = column.type
    souffle_type: str
    if isinstance(sql_type, Integer) and not column.nullable:
        souffle_type = "number"
    elif isinstance(sql_type, String) or column.nullable:
        souffle_type = "symbol"
    elif isinstance(sql_type, Text):
        souffle_type = "symbol"
    elif isinstance(sql_type, Boolean):
        souffle_type = "number"
    else:
        raise ValueError("Unexpected column type in table")
    return souffle_type


def table_to_declaration(table: Table) -> str:
    """Return the souffle datalog declaration for an SQLAlchemy table."""
    columns = [f"{col.name}: {column_to_souffle_type(col)}" for col in table.c]
    return f".decl {table.fullname[1:]} (" + ", ".join(columns) + ")"


def get_fact_declarations(metadata: MetaData) -> list[str]:
    """Return a list of fact declarations for all the mapped tables whose names begin with an '_'."""
    return [table_to_declaration(table) for table_name, table in metadata.tables.items() if table_name[0] == "_"]


def get_fact_input_statements(db_name: str, metadata: MetaData) -> list[str]:
    """Return a list of input directives for all the mapped tables beginning with an '_'."""
    return [
        f'.input {table_name[1:]} (IO=sqlite, filename="{db_name}")'
        for table_name in metadata.tables.keys()
        if table_name[0] == "_"
    ]


def get_souffle_import_prelude(db_name: str, metadata: MetaData) -> str:
    """Return souffle datalog code to import all relevant mapped tables."""
    prelude = get_fact_declarations(metadata) + get_fact_input_statements(db_name, metadata)
    return "\n".join(prelude)


def get_fact_attributes(base=ORMBase) -> str:  # type: ignore
    """Generate datalog rules which extract individual attributes from the columns of all check result tables."""
    base_decl = ".decl attribute(repository:number, check_id:symbol, attribute:symbol, value:symbol)\n "
    result = [base_decl]

    for table_name in base.metadata.tables.keys():
        table = base.metadata.tables[table_name]
        if "check" not in table_name:
            continue

        cols = table.columns
        meta = {"repository_id": "repository", "check_id": None, "id": None}

        total_num_columns = len(cols)
        for cid in range(total_num_columns):
            if cols[cid].name in meta:
                continue

            pattern = []
            col_name = cols[cid].name
            for col in cols:
                if col.name == col_name:
                    pattern.append("value")
                elif col.name in meta:
                    res = meta[col.name]
                    res = "_" if res is None else res
                    pattern.append(res)
                else:
                    pattern.append("_")

            inference = f'attribute(repository, "{table_name[1:]}", "{col_name}", value) :- '
            sfl_pattern = ",".join(pattern)
            inference += f"{table_name[1:]}({sfl_pattern})."
            result.append(inference)
    return "\n".join(result)
