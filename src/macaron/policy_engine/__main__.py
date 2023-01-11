# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
Stand-alone policy engine.

This program runs souffle against a macaron output sqlite database.
"""

import argparse
import logging
import sys
from typing import Optional

from sqlalchemy import select

from macaron.database.database_manager import DatabaseManager
from macaron.policy_engine.policy import SoufflePolicyTable
from macaron.policy_engine.souffle import SouffleError, SouffleWrapper

logger: logging.Logger = logging.getLogger(__name__)


class Config:
    """Policy engine configuration."""

    database_path: str
    interactive: bool = False
    policy_id: int | None = None
    policy_file: str | None = None


config = Config()


def policy_engine(policy: SoufflePolicyTable, override_file: Optional[str]) -> None:
    """Invoke souffle and report result."""
    with SouffleWrapper() as sfl:
        text: str = ""
        if override_file:
            with open(override_file, encoding="utf-8") as file:
                text = file.read()
        elif policy.file_text:
            text = policy.file_text
        else:
            text = ".output repository"

        try:
            res = sfl.interpret_text(policy.prelude + text)
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


def non_interactive() -> None:
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

    args = main_parser.parse_args(sys.argv[1:])

    config.database_path = args.database

    if args.interactive:
        config.interactive = args.interactive
    if args.policy_id:
        config.policy_id = args.policy_id
    if args.file:
        config.policy_file = args.file

    if config.interactive:
        interactive()
    else:
        non_interactive()

    return 0


if __name__ == "__main__":
    main()
