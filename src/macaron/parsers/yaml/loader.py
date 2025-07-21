# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the loader for YAML files."""

import logging
import os
from typing import Any

import yamale
from yamale.schema import Schema
from yaml import YAMLError

logger: logging.Logger = logging.getLogger(__name__)


class YamlLoader:
    """The loader for loading yaml content from files."""

    @staticmethod
    def _load_yaml_content(path: os.PathLike | str) -> list:
        """Load yaml content of a file using the yamale library.

        We use the default pyyaml parser for yamale.

        When loading a yaml file, this method handles printing the location that error exits (if any).
        This method does not support loading file and raw content at the same time.

        Parameters
        ----------
        path : PathLike
            The path to the yaml file we want to load.

        Returns
        -------
        list:
            The yaml content list as returned by yamale or an empty list if errors.
        """
        try:
            logger.debug("Loading yaml from file %s", path)
            return list(yamale.make_data(path))
        except YAMLError as error:
            abs_path = os.path.abspath(path)

            if hasattr(error, "problem_mark"):
                mark = error.problem_mark
                line_number = mark.line + 1
                column_number = mark.column + 1
                err_pos = f"{line_number}:{column_number}"
                logger.error("Cannot read config file %s:%s", abs_path, err_pos)
            else:
                logger.error("Cannot read config file %s", abs_path)

            return []
        except FileNotFoundError:
            logger.error("Cannot find file %s.", path)
            return []

    @classmethod
    def validate_yaml_data(cls, schema: Schema, data: list) -> bool:
        """Validate the data according to the yaml schema using the yamale library.

        Parameters
        ----------
        schema : Schema
            The yamale schema.
        data : list
            The data loaded by using ``yamale.make_data``.

        Returns
        -------
        bool
            True if the data is valid else False.
        """
        try:
            logger.debug("Validate data %s with schema %s.", str(data), str(schema.dict))
            yamale.validate(schema, data)
            return True
        except yamale.YamaleError as error:
            logger.error("Yaml data validation failed.")
            for result in error.results:
                for err_str in result.errors:
                    logger.error("\t%s", err_str)
            return False

    @classmethod
    def load(cls, path: os.PathLike | str, schema: Schema = None) -> Any:
        """Load and return a Python object from a yaml file.

        If ``schema`` is provided. This method will validate the loaded content against the
        schema.

        Parameters
        ----------
        path : os.PathLike
            The path to the yaml file.
        schema : Schema
            The schema to validate the yaml content against (default None).

        Returns
        -------
        Any
            The Python object from the yaml file or None if errors.
        """
        logger.info("Loading yaml content for %s", path)
        loaded_data = YamlLoader._load_yaml_content(path=path)
        if not loaded_data:
            logger.error("Error while loading the config yaml file %s.", path)
            return None

        if schema and not YamlLoader.validate_yaml_data(schema, loaded_data):
            logger.error("The yaml content in %s is invalid according to the schema.", path)
            return None

        result = None

        # Ensure to get the correct data
        # yamale.make_data return a list of tuples: (loaded_data, file_path).
        for data in loaded_data:
            if data[1] == path:
                result = data[0]

        return result
