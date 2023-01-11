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
    result = [
        ".decl number_attribute(repository:number, check_id:symbol, attribute:symbol, value:number)",
        ".decl symbol_attribute(repository:number, check_id:symbol, attribute:symbol, value:symbol)",
        ".decl attribute(repository:number, check_id:symbol, attribute:symbol)",
    ]

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
            col_type = column_to_souffle_type(cols[cid])
            for col in cols:
                if col.name == col_name:
                    if isinstance(col.type, Boolean):
                        pattern.append("1")
                    else:
                        pattern.append("value")
                elif col.name in meta:
                    res = meta[col.name]
                    res = "_" if res is None else res
                    pattern.append(res)
                else:
                    pattern.append("_")

            if col_type == "symbol":
                inference = f'symbol_attribute(repository, "{table_name[1:]}", "{col_name}", value) :- '
            elif isinstance(cols[cid].type, Boolean):
                inference = f'attribute(repository, "{table_name[1:]}", "{col_name}") :- '
            elif col_type == "number":
                inference = f'number_attribute(repository, "{table_name[1:]}", "{col_name}", value) :- '
            else:
                raise ValueError("not reachable")

            sfl_pattern = ",".join(pattern)
            inference += f"{table_name[1:]}({sfl_pattern})."
            result.append(inference)
    return "\n".join(result)


def get_table_rules_per_column(
    rule_name: str, table: Table, common_fields: dict[str, str], ignore_columns: list, value_type: str = "symbol"
) -> str:
    """Generate datalog rules to create subject-predicate relations from a set of columns of a table.

    Parameters
    ----------
    rule_name: str
        The name of the resulting souffle rule
    table: Table
        The sqlalchemy table to read from
    common_fields: dict[str, str]
        The table columns to be included in the relation (as the subject)
        key: the column name
        value: the corresponding relation field name
    ignore_columns: list[str]
        List of column names to be excluded from the relation
    value_type: str
        The datalog type that the value (predicate) field will have.
            Note: Symbol is nullable, number is not, numbers can be implicitly converted to symbols but not vice versa.

    """
    # Construct declaration statement
    base_decl = f".decl {rule_name} ("
    base_decl += ", ".join(
        [
            f"{field_name}:{column_to_souffle_type(table.columns[column_name])}"
            for column_name, field_name in common_fields.items()
        ]
    )
    base_decl += f", key:symbol, value:{value_type})"
    # TODO: Support all souffle types
    # This can be done by creating strValue(id, symbol), numValue(id, symbol) relations where id is created using ord()
    # on the value

    generated_lines = [base_decl]

    # Construct rule to create relations based on table
    for value_column in table.columns:
        # Loop over each column that gets treated as a value
        if value_column.name in ignore_columns:
            continue
        if value_column.name in common_fields:
            continue

        # Construct the relation statement containing all common_fields and the cid bound to value
        pattern = []
        for column in table.columns:
            if column.name == value_column.name:
                pattern.append("value")
            elif column.name in ignore_columns:
                pattern.append("_")
            elif column.name in common_fields:
                pattern.append(common_fields[column.name])
            else:
                pattern.append("_")

        lhs = f"{rule_name}(" + ",".join(common_fields.values()) + f',"{value_column.name}",value)'
        rhs = f"{table.name[1:]}(" + ",".join(pattern) + ")"
        generated_lines.append(lhs + " :- " + rhs + ".")

    return "\n".join(generated_lines)
