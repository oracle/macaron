# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module handles invoking the souffle policy engine on a database."""

import os
import sys

from sqlalchemy import MetaData, create_engine

from macaron.policy_engine.souffle import SouffleError, SouffleWrapper
from macaron.policy_engine.souffle_code_generator import (
    SouffleProgram,
    get_souffle_import_prelude,
    project_table_to_key,
    project_with_fk_join,
)
from macaron.util import logger


def get_generated(database_path: os.PathLike | str) -> SouffleProgram:
    """Get generated souffle code from database specified by configuration.

    Parameters
    ----------
    database_path: os.PathLike | str
        The path to the database to generate imports and prelude for

    Returns
    -------
    SouffleProgram
        A program containing the declarations and relations for the schema of this database

    See Also
    --------
    souffle_code_generator.py
    """
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
    """Invoke souffle and report result.

    Parameters
    ----------
    database_path: str
        The path to the database to evaluate the policy on
    policy_file: str
        The path to the policy file to evaluate

    Returns
    -------
    dict
        A dictionary containing all the relations returned by souffle mapping relation_name to the list of rows.
    """
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
