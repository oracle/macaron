# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
Stand-alone policy engine.

This program runs souffle against a macaron output sqlite database.
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Optional

from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.orm import sessionmaker

from macaron.database.database_manager import DatabaseManager
from macaron.policy_engine.policy import SoufflePolicyTable
from macaron.policy_engine.souffle import SouffleError, SouffleWrapper
from macaron.policy_engine.souffle_code_generator import (
    JsonType,
    convert_json_to_adt_row,
    get_adhoc_rules,
    get_fact_attributes,
    get_souffle_import_prelude,
)

logger: logging.Logger = logging.getLogger(__name__)


class Config:
    """Policy engine configuration."""

    database_path: str
    interactive: bool = False
    policy_id: int | None = None
    policy_file: str | None = None
    show_preamble: bool = False


global_config = Config()


class Timer:
    """Time an operation using context manager."""

    def __init__(self, name: str) -> None:
        self.start: float = time.perf_counter()
        self.name: str = name
        self.delta: float = 0.0
        self.stop: float = 0.0

    def __enter__(self) -> "Timer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        self.stop = time.perf_counter()
        self.delta = self.stop - self.start
        print(self.name, f"delta: {self.delta:0.4f}")


class JsonConverter:
    """Convert an SQLite database to json."""

    def __init__(self) -> None:
        self.metadata = MetaData()
        self.engine = create_engine(f"sqlite:///{global_config.database_path}", echo=False)
        self.metadata.reflect(self.engine)
        self.session_maker = sessionmaker(bind=self.engine)
        self.session = self.session_maker()

    def statement_to_json(self, table: Table, stmt: Any) -> JsonType:
        """Convert query result to json, back-filling foreign keys."""
        results = []

        for row in self.session.execute(stmt):
            result = {}
            for i, val in enumerate(row):
                # print(table.columns[i].name, val)

                if len(table.columns[i].foreign_keys) > 0:
                    for fork in table.columns[i].foreign_keys:
                        stmt = select(fork.column.table).where(fork.column == val)
                        result[table.columns[i].name] = self.statement_to_json(fork.column.table, stmt)
                elif "json" in table.columns[i].name.lower():
                    result[table.columns[i].name] = json.loads(val)
                else:
                    result[table.columns[i].name] = val
            results.append(result)
        if len(results) == 1:
            return results[0]
        if len(results) == 0:
            return None
        return results  # type: ignore

    def generate_json(self) -> dict:
        """Get generated souffle code from database specified by configuration."""
        prelude = get_souffle_import_prelude(global_config.database_path, self.metadata)
        prelude.update(get_fact_attributes(self.metadata))

        result: dict = {}
        for table_name in self.metadata.tables.keys():
            table = self.metadata.tables[table_name]
            result[table_name] = self.statement_to_json(table, select(table))

        return result


def get_generated() -> tuple[str, str]:
    """Get generated souffle code from database specified by configuration."""
    metadata = MetaData()
    engine = create_engine(f"sqlite:///{global_config.database_path}", echo=False)
    metadata.reflect(engine)
    session_maker = sessionmaker(bind=engine)
    session = session_maker()

    prelude = get_souffle_import_prelude(global_config.database_path, metadata)
    prelude.update(get_fact_attributes(metadata))

    result: str = str(prelude)
    result += get_adhoc_rules()
    json_facts = ""
    for table_name in metadata.tables.keys():
        table = metadata.tables[table_name]
        for column in table.columns:
            if "json" in column.name.lower():
                stmt = select(table)
                relation_name = table_name.lower().replace("_json", "").replace("json_", "")
                if relation_name[0] == "_":
                    relation_name = relation_name[1:]
                for row in session.execute(stmt):
                    res = row[column.name]
                    row_id = row["id"]
                    json_facts += (
                        "\n".join(convert_json_to_adt_row(json.loads(res), prefix=relation_name, ident=row_id)) + "\n"
                    )
    return result, json_facts


def policy_engine(policy: SoufflePolicyTable, override_file: Optional[str]) -> None:
    """Invoke souffle and report result."""
    with Timer("Codegen"):
        prelude, facts = get_generated()
    sfl = SouffleWrapper()
    text: str = ""
    if override_file:
        with open(override_file, encoding="utf-8") as file:
            text = file.read()
    elif policy.file_text:
        text = policy.file_text
    else:
        text = ".output repository"

    with open(os.path.join(sfl.fact_dir, "json.facts"), "w", encoding="utf-8") as file:
        file.write(facts)

    prelude += '\n.input json (filename="json.facts")\n'

    if global_config.show_preamble:
        print(prelude)
        return

    try:
        with Timer("Souffle"):
            res = sfl.interpret_text(prelude + text)
    except SouffleError as error:
        print(error.command)
        print(error.message)
        sys.exit(1)

    for key, values in res.items():
        print(key)
        for value in values:
            print("    ", value)


def interactive() -> None:
    """Interactively evaluate a policy file, REPL."""
    raise NotImplementedError()


def non_interactive(config: Config = global_config) -> None:
    """Evaluate a policy based on configuration and exit."""
    with DatabaseManager(config.database_path) as dbman:
        stmt = select(SoufflePolicyTable)
        if config.policy_id:
            stmt = select(SoufflePolicyTable).where(SoufflePolicyTable.id == config.policy_id)

        for result in dbman.session.scalars(stmt):
            policy_engine(result, override_file=config.policy_file)


def main() -> int:
    """Parse arguments and start policy engine."""
    main_parser = argparse.ArgumentParser(prog="policy_engine")
    main_parser.add_argument("-d", "--database", help="Database path", required=True, action="store")
    main_parser.add_argument("-i", "--interactive", help="Run in interactive mode", required=False, action="store_true")
    main_parser.add_argument("-po", "--policy-id", help="The policy id to evaluate", required=False, action="store")
    main_parser.add_argument("-f", "--file", help="Replace policy file", required=False, action="store")
    main_parser.add_argument("-s", "--show-preamble", help="Show preamble", required=False, action="store_true")

    args = main_parser.parse_args(sys.argv[1:])

    global_config.database_path = args.database

    if args.interactive:
        global_config.interactive = args.interactive
    if args.policy_id:
        global_config.policy_id = args.policy_id
    if args.file:
        global_config.policy_file = args.file
    if args.show_preamble:
        global_config.show_preamble = args.show_preamble

    if global_config.interactive:
        interactive()
    else:
        non_interactive()

    return 0


if __name__ == "__main__":
    main()
