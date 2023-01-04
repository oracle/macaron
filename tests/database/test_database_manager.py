# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module test DatabaseManager
"""

from pathlib import Path
from unittest import TestCase

from macaron.database.database_manager import DatabaseManager


class TestDatabaseManager(TestCase):
    """
    Test the DatabaseManager module.
    """

    def setUp(self) -> None:
        db_path = str(Path(__file__).parent.joinpath("macaron.db"))
        self.db_man = DatabaseManager(db_path)

    def tearDown(self) -> None:
        self.db_man.terminate()
