# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
Policy engine Command Line Interface (CLI).

This program runs souffle against a macaron output sqlite database.
"""

import argparse
import logging
import os
import sys
import time
from typing import Never

from sqlalchemy import MetaData, create_engine

from macaron.policy_engine.souffle import SouffleError, SouffleWrapper
from macaron.policy_engine.souffle_code_generator import (
    SouffleProgram,
    get_souffle_import_prelude,
    project_table_to_key,
    project_with_fk_join,
)

logger: logging.Logger = logging.getLogger(__name__)


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
        logger.debug("%s delta: %s", self.name, f"{self.delta:0.4f}")


def get_generated(database_path: os.PathLike | str) -> SouffleProgram:
    """Get generated souffle code from database specified by configuration."""
    if not os.path.isfile(database_path):
        logger.error("Unable to open database %s", database_path)
        sys.exit(1)

    metadata = MetaData()
    engine = create_engine(f"sqlite:///{database_path}", echo=False)
    metadata.reflect(engine)

    prelude = get_souffle_import_prelude(os.path.abspath(database_path), metadata)

    for table_name in metadata.tables.keys():
        table = metadata.tables[table_name]
        if table_name[0] == "_":
            prelude.update(project_table_to_key(f"{table_name[1:]}_attribute", table))
            prelude.update(project_with_fk_join(table))

    return prelude


def copy_prelude(database_path: os.PathLike | str, sfl: SouffleWrapper, prelude: SouffleProgram | None = None) -> None:
    """
    Generate and copy the prelude into the souffle instance's include directory.

    Parameters
    ----------
    database_path: os.PathLike | str
        The path to the database the facts will be imported from
    sfl: SouffleWrapper
        The souffle execution context object
    prelude: SouffleProgram | None
        Optional, the prelude to use for the souffle program, if none is given the default prelude is generated from
        the database at database_path.
    """
    if prelude is None:
        prelude = get_generated(database_path)
    sfl.copy_to_includes("import_data.dl", str(prelude))

    folder = os.path.join(os.path.dirname(__file__), "prelude")
    for file_name in os.listdir(folder):
        full_file_name = os.path.join(folder, file_name)
        if not os.path.isfile(full_file_name):
            continue
        with open(full_file_name, encoding="utf-8") as file:
            text = file.read()
            sfl.copy_to_includes(file_name, text)


def policy_engine(database_path: str, policy_file: str) -> dict:
    """Invoke souffle and report result."""
    with SouffleWrapper() as sfl:
        copy_prelude(database_path, sfl)
        with open(policy_file, encoding="utf-8") as file:
            text = file.read()

        try:
            res = sfl.interpret_text(text)
        except SouffleError as error:
            logger.error("COMMAND: %s", error.command)
            logger.error("ERROR: %s", error.message)
            sys.exit(1)

        return res


def non_interactive(database_path: str, show_prelude: bool, policy_file: str) -> bool:
    """Evaluate a policy based on configuration and exit."""
    if show_prelude:
        prelude = get_generated(database_path)
        logger.info("\n%s", prelude)
        return False

    res = policy_engine(database_path, policy_file)

    output = []
    for key, values in res.items():
        output.append(str(key))
        for value in values:
            output.append(f"    {value}")

    logger.info("Policy results:\n%s", "\n".join(output))

    return any(res["failed_policies"])


def main() -> Never:
    """Parse arguments and start policy engine."""
    main_parser = argparse.ArgumentParser(prog="policy_engine")
    main_parser.add_argument("-d", "--database", help="Database path", required=True, action="store")
    main_parser.add_argument("-f", "--file", help="Replace policy file", required=False, action="store")
    main_parser.add_argument("-s", "--show-prelude", help="Show policy prelude", required=False, action="store_true")
    main_parser.add_argument("-v", "--verbose", help="Enable verbose logging", required=False, action="store_true")
    main_parser.add_argument("-l", "--log-path", help="Log file path", required=False, action="store")

    args = main_parser.parse_args(sys.argv[1:])

    if args.verbose:
        log_level = logging.DEBUG
        log_format = "%(asctime)s [%(name)s:%(funcName)s:%(lineno)d] [%(levelname)s] %(message)s"
    else:
        log_level = logging.INFO
        log_format = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(format=log_format, handlers=[logging.StreamHandler()], force=True, level=log_level)

    if args.log_path:
        debug_log_path = os.path.abspath(args.log_path)
        log_file_handler = logging.FileHandler(debug_log_path, "w")
        log_file_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(log_file_handler)
        logger.info("The log file of the policy engine be stored in %s", debug_log_path)

    database_path = args.database
    policy_file = ""
    show_prelude = False

    if args.file:
        policy_file = args.file
    if args.show_prelude:
        show_prelude = args.show_prelude

    res = non_interactive(database_path, show_prelude, policy_file)
    sys.exit(res)


if __name__ == "__main__":
    main()
