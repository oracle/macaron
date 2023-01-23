# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Generate souffle datalog for policy prelude."""
from typing import TypeGuard

from sqlalchemy import Column, MetaData, Table
from sqlalchemy.sql.sqltypes import Boolean, Integer, String, Text

from macaron.util import JsonType, logger


def get_adhoc_rules() -> str:
    """Get special souffle rules for preamble."""
    return """
.decl check_passed(repository: number, check_name: symbol)
check_passed(repo, check) :- check_name(check), repository_attribute(repo, cat(check, ".passed"), $Bool(1)).


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
    if isinstance(sql_type, Integer):
        souffle_type = "number"
    elif isinstance(sql_type, String):
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


def get_fact_declarations(metadata: MetaData) -> SouffleProgram:
    """Return a list of fact declarations for all the mapped tables whose names begin with an '_'."""
    return SouffleProgram(
        declarations={
            table_to_declaration(table) for table_name, table in metadata.tables.items() if table_name[0] == "_"
        }
    )


def get_fact_input_statements(db_name: str, metadata: MetaData) -> SouffleProgram:
    """Return a list of input directives for all the mapped tables beginning with an '_'."""
    return SouffleProgram(
        directives={
            f'.input {table_name[1:]} (IO=sqlite, filename="{db_name}")'
            for table_name in metadata.tables.keys()
            if table_name[0] == "_"
        }
    )


def get_souffle_import_prelude(db_name: str, metadata: MetaData) -> SouffleProgram:
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

                    if col.nullable or isinstance(col.type, String):
                        value_statement = "$String(value)"
                    elif isinstance(col.type, Integer):
                        value_statement = "$Int(value)"
                    elif isinstance(col.type, Boolean):
                        value_statement = "$Bool(value)"
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
            if column.name == value_column.name:
                if isinstance(column.type, String):
                    value_statement = "$String(value)"
                    pattern.append("value")
                elif isinstance(column.type, Integer):
                    value_statement = "$Int(value)"
                    pattern.append("value")
                elif isinstance(column.type, Boolean):
                    value_statement = "$Bool(value)"
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


def project_table_to_key(relation_name: str, table: Table) -> SouffleProgram:
    """Create rules to convert a table to an attribute that maps its primary keys to its columns."""
    if len(table.columns) <= len(table.primary_key.columns):
        return SouffleProgram()

    common_fields: dict[str, str] = {col.name: col.name for col in table.primary_key.columns}
    ignore_columns: list = []

    return get_table_rules_per_column(relation_name, table, common_fields, ignore_columns)


# We generate ADT facts for inputting a json document to souffle as a text inclusion.
#
# For example: {"index": ["value"]} becomes
#
#       $Object("index", $Array(0, $String("value")))
#
# Directly generating these facts is the best option since souffle only supports csv input for ADTs, and the csv
# representation of ADTs is their literal representation in souffle datalog.
# Json can alternatively be represented simply as the leaves and their corresponding addresses in the document,
#
#       jsonDocument(id, "input.index[0]", "value")
#
# This representation is also automatically inferred from the ADT representation.
#
# Note: since it is advantageous to be able to refer to any element in the document, an alternative representation to
# consider could be using relations between each element in the document:
#
#       object(id0)
#       objectElem(id0, "index", id1),
#       array(id1)
#       arrayElem(id1, 0, stringElement(id2))
#       stringElem(id2, "value")
#


class WalkerState:
    """Class to store a stack of the json field address and convert it to an ADT."""

    docname: str
    state_sequence: list[str | int]

    def __init__(self) -> None:
        self.state_sequence = []

    def get_str_state_sequence(self) -> str:
        """Get object/array the dereference sequence for the current leaf, as a string."""
        return "".join([f"[{x}]" if isinstance(x, int) else f".{x}" for x in self.state_sequence])[1:]

    def wrap_sequence_adt(self, state_sequence: list[int | str], value: str) -> str:
        """Wrap the value in the recursive ADT JSON Type literal specified by state_sequence."""
        if len(state_sequence) == 0:
            return value

        last = state_sequence.pop()
        if isinstance(last, int):
            return self.wrap_sequence_adt(state_sequence, f"$Array({last}, {value})")

        return self.wrap_sequence_adt(state_sequence, f'$Object("{last}", {value})')

    def escape_string(self, string: str) -> str:
        """Escape a string for souffle fact."""
        # More recent souffle supports string escaping, but currently does not
        return string.replace("\n", "\\n").replace('"', "'")

    def wrap_value(self, value: JsonType) -> str:
        """Wrap a python value in the souffle ADT type for that value (not array or object)."""
        val_adt = {int: "$Int", float: "$Float", str: "$String", type(None): "$null", bool: "$Bool"}[type(value)]
        if isinstance(value, str):
            val_adt += f'("{self.escape_string(value)}")'
        elif isinstance(value, bool):
            val_adt += f"({int(value)})"
        elif value is None:
            val_adt += ""
        else:
            val_adt += f"({value})"
        return val_adt

    def get_adt(self, value: JsonType) -> str:
        """Get the adt literal for the value using the current state sequence."""
        val_adt = self.wrap_value(value)
        return self.wrap_sequence_adt(self.state_sequence.copy(), val_adt)

    def add(self, elems: int | str) -> None:
        """Push an object/array lookup onto the stack."""
        self.state_sequence.append(elems)

    def remove(self, num: int = 1) -> None:
        """Remove n object/array lookups from the stack."""
        for _i in range(num):
            self.state_sequence.pop()


def _is_json_array(obj: JsonType) -> TypeGuard[list[int]]:
    return isinstance(obj, list)


def _is_json_object(obj: JsonType) -> TypeGuard[dict[str, JsonType]]:
    return isinstance(obj, dict)


def _json_to_facts(state: WalkerState, ast: JsonType | dict[str, JsonType] | list[JsonType]) -> list[str]:
    """Walk the json document (ast) and return the list of leaves and their addresses."""
    results = []
    if _is_json_array(ast):
        for k, val in enumerate(ast):
            state.add(k)
            results += _json_to_facts(state, val)
            state.remove()
    elif _is_json_object(ast):
        for i, val2 in ast.items():
            state.add(i)
            results += _json_to_facts(state, val2)
            state.remove()
    else:
        return [state.get_adt(ast)]

    return results


def convert_json_to_adt_row(data: JsonType, prefix: str = "input", ident: int = 0) -> list[str]:
    """Convert a json document to the souffle ADT fact in csv format."""
    return [f'"{prefix}"\t{ident}\t{adt}' for adt in _json_to_facts(WalkerState(), data)]


def convert_json_to_adt_fact(data: JsonType, prefix: str = "input", ident: int = 0) -> list[str]:
    """Convert a json document to the souffle ADT fact literal."""
    return [f'json("{prefix}",{ident},{adt}).' for adt in _json_to_facts(WalkerState(), data)]
