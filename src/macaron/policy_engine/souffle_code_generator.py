# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Generate souffle datalog for policy prelude."""

import os

from sqlalchemy import Column, MetaData, Table
from sqlalchemy.sql.sqltypes import Boolean, Integer, String, Text

from macaron.util import logger


def get_adhoc_rules() -> str:
    """Get special souffle rules for preamble."""
    return """

.decl transitive_dependency(repo: number, dependency: number)

transitive_dependency(repo, dependency) :- dependency(repo, dependency).
transitive_dependency(repo, dependency) :-
    transitive_dependency(repo, a), transitive_dependency(a, dependency).

#define any(x) count: {x} > 1
#define all(x, y) count: {x} = count: {x, y}

.type JsonType = Int {x : number}
         | String {x : symbol}
         | Float {x : float}
         | Bool {x : number}
         | null {}
         | Object {x: symbol, y : JsonType}
         | Array {x : number, y : JsonType}

.decl json(name: symbol, id: number, root: JsonType)

.decl any_terminal(s:symbol, k:symbol)

.decl json_path(j: JsonType, a: JsonType, key:symbol)

json_path(a, b, key) :- a = $Object(k, b), json(name,_,a), key=cat(name, cat(".", k)).
json_path(a, b, key) :- a = $Array(k, b), json(name,_,a), key=cat(name, cat("[", cat(to_string(k), "]"))).

json_path(a, b, key) :- a = $Object(k, b), json(_,_,c), json_path(c,a,kb), key=cat(cat(kb, "."),k).
json_path(a, b, key) :- a = $Array(k, b), json(_,_,c), json_path(c,a,kb),key=cat(kb, cat(cat("[",to_string(k)), "]")).

json_path(a, b,key) :- json_path(a,c,_), json_path(c, b, kb), key=kb.

any_terminal(s,k) :- json(_,_,r), json_path(r, $String(s), k).

.decl json_number(name: symbol, json:number, addr: symbol, k:number)
.decl json_symbol(name:symbol, json:number, addr: symbol, k:symbol)

json_number(name, js, addr, val) :- json(name, js, r), json_path(r, $Int(val), addr).
json_symbol(name, js, addr, val) :- json(name, js, r), json_path(r, $String(val), addr).
"""


class SouffleProgram:
    """Class to store generated souffle datalog program."""

    declarations: set[str]
    directives: set[str]
    rules: set[str]

    def __init__(
        self, declarations: None | set[str] = None, directives: None | set[str] = None, rules: None | set[str] = None
    ):
        self.declarations = set()
        self.directives = set()
        self.rules = set()
        if rules is not None:
            self.rules = rules
        if directives is not None:
            self.directives = directives
        if declarations is not None:
            self.declarations = declarations

    def update(self, other: "SouffleProgram") -> "SouffleProgram":
        """Merge another program into this one."""
        self.declarations = self.declarations.union(other.declarations)
        self.directives = self.directives.union(other.directives)
        self.rules = self.rules.union(other.rules)

        return self

    def __str__(self) -> str:
        return "\n".join(list(self.declarations) + list(self.directives) + list(self.rules))


def column_to_souffle_type(column: Column) -> str:
    """Return a souffle type string for a SQLAlchemy Column."""
    sql_type = column.type
    souffle_type: str
    if isinstance(sql_type, String) or column.nullable:
        souffle_type = "symbol"
    elif isinstance(sql_type, Integer):
        souffle_type = "number"
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


def get_fact_declarations(metadata: MetaData) -> SouffleProgram:
    """Return a list of fact declarations for all the mapped tables whose names begin with an '_'."""
    return SouffleProgram(
        declarations={
            table_to_declaration(table) for table_name, table in metadata.tables.items() if table_name[0] == "_"
        }
    )


def get_fact_input_statements(db_name: os.PathLike | str, metadata: MetaData) -> SouffleProgram:
    """Return a list of input directives for all the mapped tables beginning with an '_'."""
    return SouffleProgram(
        directives={
            f'.input {table_name[1:]} (IO=sqlite, filename="{db_name}")'
            for table_name in metadata.tables.keys()
            if table_name[0] == "_"
        }
    )


def get_souffle_import_prelude(db_name: os.PathLike | str, metadata: MetaData) -> SouffleProgram:
    """Return souffle datalog code to import all relevant mapped tables."""
    return get_fact_declarations(metadata).update(get_fact_input_statements(db_name, metadata))


def get_fact_attributes(metadata: MetaData) -> SouffleProgram:
    """Generate datalog rules which extract individual attributes from the columns of all check result tables."""
    result = SouffleProgram(
        declarations={
            ".decl repository_attribute (id:number, key:symbol, value:JsonType)",
            ".decl check_name(name:symbol)"
            # ".decl symbol_attribute(repository:number, check_id:symbol, attribute:symbol, value:symbol)",
            # ".decl attribute(repository:number, check_id:symbol, attribute:symbol)",
        }
    )

    for table_name in metadata.tables.keys():
        table = metadata.tables[table_name]
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
            value_statement = "value"
            for col in cols:
                if col.name == col_name:

                    if col_type == "symbol":
                        value_statement = "$String(value)"
                    elif col_type == "number":
                        value_statement = "$Int(value)"
                    else:
                        logger.error("Unknown column type in codegen.")
                        value_statement = "$String(value)"
                    pattern.append("value")
                elif col.name in meta:
                    res = meta[col.name]
                    res = "_" if res is None else res
                    pattern.append(res)
                else:
                    pattern.append("_")

            result.rules.add(f'check_name("{table_name[1:]}").')
            inference = f'repository_attribute(repository, "{table_name[1:]}.{col_name}", {value_statement}) :- '
            if col_type == "symbol":
                inference += 'value != "n/a", '

            sfl_pattern = ",".join(pattern)
            inference += f"{table_name[1:]}({sfl_pattern})."
            result.rules.add(inference)
    return result


def project_join_table_souffle_relation(
    rule_name: str,
    left_table: Table,
    left_common_fields: dict[str, str],
    right_table: Table,
    right_common_fields: dict[str, str],
    right_ignore_fields: list[str],
    prefix_table_name_to_key: bool = True,
) -> SouffleProgram:
    """Generate souffle datalog to join two tables together.

    This creates a relation that will appear as

        rule_name(left, common, fields, "right_column_name", right_column_value) :-
            left_relation(left, common, _, fields, _), right_relation(right_column_value, _ ...).
        rule_name(left, common, fields, "right_column_name_2", right_column_value) :-
            left_relation(left, common, _, fields, _), right_relation(_, right_column_value, ...).

    Parameters
    ----------
    rule_name: str
        The name of the rule to generate
    left_table: Table
        The table to appear on the left of the relation (the "subject")
    left_common_fields: dict[str, str]
        The columns to include on the left of the relation, mapped to the names they should have in the declaration
    right_table: Table
        The table on the right hand side of the relation (the "predicate")
    right_common_fields: dict[str, str]
        The columns from the right table that should appear on the left of the relation
    right_ignore_fields: list[str]
        The columns that should not appear in the relation
    prefix_table_name_to_key: bool
        Should the key field of the relation be prefixed with the table name: so that it appears as
        "tableName.columnName"
    """
    result = SouffleProgram(
        declarations={
            f".decl {rule_name} ("
            + ", ".join(
                [
                    f"{field_name}:{column_to_souffle_type(left_table.columns[column_name])}"
                    for column_name, field_name in left_common_fields.items()
                ]
                + [
                    f"{field_name}:{column_to_souffle_type(left_table.columns[column_name])}"
                    for column_name, field_name in right_common_fields.items()
                ]
            )
            + ", key:symbol, value:JsonType)"
        }
    )

    # Construct rule to create relations based on table
    for value_column in right_table.columns:
        # Loop over each column that gets treated as a value
        if value_column.name in right_ignore_fields:
            continue
        if value_column.name in right_common_fields:
            continue

        # Construct the relation statement containing all common_fields and the cid bound to value
        right_pattern = []
        left_pattern = []
        value_statement = ""

        # Construct the relation statement containing all common_fields and the cid bound to value
        for column in left_table.columns:
            if column.name in left_common_fields:
                left_pattern.append(left_common_fields[column.name])
            else:
                left_pattern.append("_")

        value_statement = ""
        for column in right_table.columns:
            col_type = column_to_souffle_type(column)
            if column.name == value_column.name:
                if col_type == "symbol":
                    value_statement = "$String(value)"
                    right_pattern.append("value")
                elif col_type == "number":
                    value_statement = "$Int(value)"
                    right_pattern.append("value")
                else:
                    logger.error("Unknown column type in codegen.")
                    value_statement = "$String(value)"
                    right_pattern.append("value")

            elif column.name in right_ignore_fields:
                right_pattern.append("_")
            elif column.name in right_common_fields:
                right_pattern.append(right_common_fields[column.name])
            else:
                right_pattern.append("_")

        key_literal = value_column.name
        if prefix_table_name_to_key:
            key_literal = value_column.table.name[1:] + "." + key_literal
        lhs = (
            f"{rule_name}("
            + ",".join(list(left_common_fields.values()) + list(right_common_fields.values()))
            + f',"{key_literal}", {value_statement})'
        )
        rhs_left_table = f"{left_table.name[1:]}(" + ",".join(left_pattern) + ")"
        rhs_right_table = f"{right_table.name[1:]}(" + ",".join(right_pattern) + ")"
        rule_stmt = lhs + " :- " + rhs_left_table + ", " + rhs_right_table + "."
        result.rules.add(rule_stmt)
    return result


def get_table_rules_per_column(
    rule_name: str, table: Table, common_fields: dict[str, str], ignore_columns: list
) -> SouffleProgram:
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

    result = SouffleProgram(
        declarations={
            f".decl {rule_name} ("
            + ", ".join(
                [
                    f"{field_name}:{column_to_souffle_type(table.columns[column_name])}"
                    for column_name, field_name in common_fields.items()
                ]
            )
            + ", key:symbol, value:JsonType)"
        }
    )

    # Construct rule to create relations based on table
    for value_column in table.columns:
        # Loop over each column that gets treated as a value
        if value_column.name in ignore_columns:
            continue
        if value_column.name in common_fields:
            continue

        # Construct the relation statement containing all common_fields and the cid bound to value
        pattern = []
        value_statement = ""
        for column in table.columns:
            col_type = column_to_souffle_type(column)
            if column.name == value_column.name:
                if col_type == "symbol":
                    value_statement = "$String(value)"
                    pattern.append("value")
                elif col_type == "number":
                    value_statement = "$Int(value)"
                    pattern.append("value")
                else:
                    logger.error("Unknown column type in codegen.")
                    value_statement = "$String(value)"
                    pattern.append("value")

            elif column.name in ignore_columns:
                pattern.append("_")
            elif column.name in common_fields:
                pattern.append(common_fields[column.name])
            else:
                pattern.append("_")

        lhs = f"{rule_name}(" + ",".join(common_fields.values()) + f',"{value_column.name}",{value_statement})'
        rhs = f"{table.name[1:]}(" + ",".join(pattern) + ")"
        rule_stmt = lhs + " :- " + rhs + "."
        result.rules.add(rule_stmt)

    return result


def project_with_fk_join(table: Table) -> SouffleProgram:
    """Create attribute relations joining on foreign keys.

    For each foreign key in this table, creates a relation for the reference table which receives this table's values.
    """
    if len(table.columns) <= len(table.primary_key.columns):
        return SouffleProgram()

    program = SouffleProgram()

    for foreign_key in table.foreign_keys:
        left_table = foreign_key.column.table
        left_common_fields: dict[str, str] = {col.name: col.name for col in left_table.primary_key.columns}
        right_ignore_fields: list[str] = [col.name for col in table.primary_key.columns]
        program.update(
            project_join_table_souffle_relation(
                f"{left_table.name[1:]}_attribute", left_table, left_common_fields, table, {}, right_ignore_fields
            )
        )

    return program


def project_table_to_key(relation_name: str, table: Table) -> SouffleProgram:
    """Create rules to convert a table to an attribute that maps its primary keys to its columns."""
    if len(table.columns) <= len(table.primary_key.columns):
        return SouffleProgram()

    common_fields: dict[str, str] = {col.name: col.name for col in table.primary_key.columns}
    ignore_columns: list = []

    return get_table_rules_per_column(relation_name, table, common_fields, ignore_columns)
