# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the MacaronTestCase class for setup/teardown of test cases."""

import os
from pathlib import Path
from unittest import TestCase

import macaron
from macaron.config.defaults import create_defaults, defaults, load_defaults


# TODO: add fixture in the future
class MacaronTestCase(TestCase):
    """The TestCase class for Macaron."""

    macaron_path: Path = Path(macaron.MACARON_PATH)
    """The root path of Macaron."""

    macaron_test_dir: Path = Path(__file__).parent
    """The tests/ directory from the root path of Macaron."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up the necessary values for the tests."""
        # Load values from defaults.ini.
        if not cls.macaron_test_dir.joinpath("defaults.ini").exists():
            create_defaults(str(cls.macaron_test_dir), str(cls.macaron_path))

        load_defaults(os.path.join(str(cls.macaron_test_dir), "defaults.ini"))

    @classmethod
    def tearDownClass(cls) -> None:
        """Clean up the values in defaults.ini."""
        defaults.clear()
