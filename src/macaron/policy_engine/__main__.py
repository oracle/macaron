# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
Stand-alone policy engine.

This program runs souffle against a macaron output sqlite database.
"""

import argparse
import logging
import sys
import time

from sqlalchemy import MetaData, create_engine

from macaron.policy_engine.souffle import SouffleError, SouffleWrapper
from macaron.policy_engine.souffle_code_generator import (
    get_adhoc_rules,
    get_souffle_import_prelude,
    project_table_to_key,
    project_with_fk_join,
)

logger: logging.Logger = logging.getLogger(__name__)


class Config:
    """Policy engine configuration."""

    database_path: str
    interactive: bool = False
    policy_id: int | None = None
    policy_file: str | None = None
    show_prelude: bool = False


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


def get_generated(database_path: str) -> str:
    """Get generated souffle code from database specified by configuration."""
    metadata = MetaData()
    engine = create_engine(f"sqlite:///{database_path}", echo=False)
    metadata.reflect(engine)

    prelude = get_souffle_import_prelude(database_path, metadata)

    for table_name in metadata.tables.keys():
        table = metadata.tables[table_name]
        if table_name[0] == "_":
            prelude.update(project_table_to_key(f"{table_name[1:]}_attribute", table))
            prelude.update(project_with_fk_join(table))

    result: str = str(prelude)
    result += get_adhoc_rules()

    return result


def policy_engine(config: type[Config], policy_file: str) -> dict:
    """Invoke souffle and report result."""
    with Timer("Codegen"):
        prelude = get_generated(config.database_path)
    sfl = SouffleWrapper()
    with open(policy_file, encoding="utf-8") as file:
        text = file.read()

    if config.show_prelude:
        print(prelude)
        return {}

    try:
        with Timer("Souffle"):
            res = sfl.interpret_text(prelude + text)
    except SouffleError as error:
        print(error.command)
        print(error.message)
        sys.exit(1)

    return res


def interactive() -> None:
    """Interactively evaluate a policy file, REPL."""
    raise NotImplementedError()


def non_interactive(config: Config = global_config) -> None:
    """Evaluate a policy based on configuration and exit."""
    if config.policy_file:
        res = policy_engine(config, config.policy_file)  # type: ignore

        for key, values in res.items():
            print(key)
            for value in values:
                print("    ", value)
        return

    raise ValueError("No policy file specified.")


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
        global_config.show_prelude = args.show_preamble

    if global_config.interactive:
        interactive()
    else:
        non_interactive()

    return 0


if __name__ == "__main__":
    main()
