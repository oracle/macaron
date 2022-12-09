# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Configuration class for the target analyzed repository."""

import logging
import os
from typing import Any

import yamale
from yamale.schema import Schema

logger: logging.Logger = logging.getLogger(__name__)

_SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "target_config_schema.yaml")

TARGET_CONFIG_SCHEMA: Schema = yamale.make_schema(_SCHEMA_DIR)
"""The schema for the target configuration yaml file."""


class Configuration:
    """This class contains the configuration for an analyzed repo in Macaron."""

    def __init__(self, data: dict = None) -> None:
        """Construct the Configuration object.

        Parameters
        ----------
        data : dict
            The dictionary contains the data to analyze a repository.
        """
        self.options = {"id": "", "path": "", "branch": "", "digest": "", "note": "", "available": ""}

        if data:
            for key, value in data.items():
                self.options[key] = value

    def set_value(self, key: str, value: Any) -> None:
        """Set an option in the configuration.

        Parameters
        ----------
        key : str
            The key to insert value.
        value : Any
            The value to insert.
        """
        self.options[key] = value

    def get_value(self, key: str) -> Any:
        """Get an option value in the configuration.

        Parameters
        ----------
        key : str
            The key to get the value.

        Returns
        -------
        Any
            The value indicated by key or None if not existed.
        """
        return self.options.get(key)
