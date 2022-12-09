# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module test the yaml loader functions."""

import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import yamale
from yamale import YamaleError
from yamale.schema import Schema
from yaml import YAMLError

from macaron.parsers.yaml.loader import YamlLoader


# pylint: disable=protected-access
class TestYamlLoader(TestCase):
    """Test the YamlLoader class."""

    RESOURCES_DIR = Path(__file__).parent.joinpath("resources")

    def test_load_yaml_content(self) -> None:
        """Test the load yaml content method."""
        # Valid content
        with patch("yamale.make_data", return_value=[({"yaml": None}, None)]):
            assert YamlLoader._load_yaml_content("sample_file_path") == [({"yaml": None}, None)]

        # Failed while loading the yaml file
        with patch("yamale.make_data", side_effect=YAMLError):
            assert YamlLoader._load_yaml_content("sample_file_path") == []

        # File not found
        with patch("yamale.make_data", side_effect=FileNotFoundError):
            assert YamlLoader._load_yaml_content("sample_file_path") == []

    def test_validate_yaml_data(self) -> None:
        """Test the validate yaml data method."""
        # We are not testing the behavior of yamale methods
        # so the schema and data can be empty
        mock_schema = Schema({})
        mock_data: list = []

        # No errors
        with patch("yamale.validate", return_value=[]):
            assert YamlLoader.validate_yaml_data(mock_schema, mock_data)

        # Errors exist
        with patch("yamale.validate", side_effect=YamaleError(results=[])):
            assert not YamlLoader.validate_yaml_data(mock_schema, mock_data)

    def test_load(self) -> None:
        """Test the load method of YamlLoader."""
        schema_file = os.path.join(self.RESOURCES_DIR, "schema.yaml")
        schema: Schema = yamale.make_schema(schema_file)

        assert not YamlLoader.load(os.path.join(self.RESOURCES_DIR, "invalid.yaml"))
        assert not YamlLoader.load(os.path.join(self.RESOURCES_DIR, "invalid.yaml"), schema)

        assert YamlLoader.load(os.path.join(self.RESOURCES_DIR, "valid_against_schema.yaml"))
        assert not YamlLoader.load(os.path.join(self.RESOURCES_DIR, "valid_against_schema.yaml"), schema)

        assert YamlLoader.load(os.path.join(self.RESOURCES_DIR, "not_valid_against_schema.yaml"))
        assert YamlLoader.load(os.path.join(self.RESOURCES_DIR, "not_valid_against_schema.yaml"), schema)
