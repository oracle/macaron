# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Configuration class for the target analyzed repository."""

import logging
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)

"""The schema for the target configuration yaml file."""


class Configuration:
    """This class contains the configuration for an analyzed repo in Macaron."""

    def __init__(self, data: dict | None = None) -> None:
        """Construct the Configuration object.

        Parameters
        ----------
        data : dict | None
            The dictionary contains the data to analyze a repository.
        """
        self.options = {"id": "", "purl": "", "path": "", "branch": "", "digest": "", "note": "", "available": ""}

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
