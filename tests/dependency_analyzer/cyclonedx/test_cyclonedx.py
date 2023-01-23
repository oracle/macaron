# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the CyclondeDX helper functions."""

import json
import os
from pathlib import Path

from macaron.dependency_analyzer.cyclonedx import (
    CycloneDXParserError,
    convert_components_to_artifacts,
    deserialize_bom_json,
    get_dep_components,
)
from tests.macaron_testcase import MacaronTestCase


class TestCyclondeDX(MacaronTestCase):
    """Test the CyclondeDX helper functions."""

    RESOURCES_DIR = Path(__file__).parent.joinpath("resources")
    EXPECTED_DIR = Path(__file__).parent.joinpath("expected_results")

    def test_deserialize_bom_json(self) -> None:
        """Test deserializing a bom.json file."""
        # Deserialize a valid bom.json.
        path = Path(TestCyclondeDX.RESOURCES_DIR, "valid_bom.json")
        deserialize_bom_json(path)

        # Deserialize a bom.json that does not exist.
        path = Path(TestCyclondeDX.RESOURCES_DIR, "does_not_exist")
        self.assertRaises(CycloneDXParserError, deserialize_bom_json, path)

        # Deserialize an invalid bom.json.
        path = Path(TestCyclondeDX.RESOURCES_DIR, "invalid_bom.json")
        self.assertRaises(CycloneDXParserError, deserialize_bom_json, path)

    @classmethod
    def test_get_dep_components(cls) -> None:
        """Test retrieving dependencies as components."""
        # Path to the root bom.json.
        root_bom_path = Path(cls.RESOURCES_DIR, "root_bom.json")

        # Path to the sub-project bom.json files.
        child_bom_paths = [Path(cls.RESOURCES_DIR, "child_bom_1.json"), Path(cls.RESOURCES_DIR, "child_bom_2.json")]

        # Pass a single bom.json file.
        with open(os.path.join(cls.EXPECTED_DIR, "deps_components_1.json"), encoding="utf-8") as file:
            expected_result = json.load(file)
            expected_bom_refs = sorted(res["bom-ref"] for res in expected_result)
            result_bom_refs = sorted(res["bom-ref"] for res in get_dep_components(root_bom_path=root_bom_path))
            assert expected_bom_refs == result_bom_refs

        # Pass a single bom.json file in recursive mode.
        with open(os.path.join(cls.EXPECTED_DIR, "deps_components_2.json"), encoding="utf-8") as file:
            expected_result = json.load(file)
            expected_bom_refs = sorted(res["bom-ref"] for res in expected_result)
            result_bom_refs = sorted(
                res["bom-ref"] for res in get_dep_components(root_bom_path=root_bom_path, recursive=True)
            )
            assert expected_bom_refs == result_bom_refs

        # Pass a root bom.json and two sub-project bom.json files.
        with open(os.path.join(cls.EXPECTED_DIR, "deps_components_3.json"), encoding="utf-8") as file:
            expected_result = json.load(file)
            expected_bom_refs = sorted(res["bom-ref"] for res in expected_result)
            result_bom_refs = sorted(
                res["bom-ref"]
                for res in get_dep_components(root_bom_path=root_bom_path, child_bom_paths=child_bom_paths)
            )
            assert expected_bom_refs == result_bom_refs

        # Pass a root bom.json and two sub-project bom.json files in recursive mode.
        with open(os.path.join(cls.EXPECTED_DIR, "deps_components_4.json"), encoding="utf-8") as file:
            expected_result = json.load(file)
            expected_bom_refs = sorted(res["bom-ref"] for res in expected_result)
            result_bom_refs = sorted(
                res["bom-ref"]
                for res in get_dep_components(
                    root_bom_path=root_bom_path, child_bom_paths=child_bom_paths, recursive=True
                )
            )
            assert expected_bom_refs == result_bom_refs

    @classmethod
    def test_convert_components_to_artifacts(cls) -> None:
        """Test converting CycloneDX components using internal artifact representation."""
        # Path to the root bom.json.
        root_bom_path = Path(cls.RESOURCES_DIR, "root_bom.json")

        # Path to the sub-project bom.json files.
        child_bom_paths = [Path(cls.RESOURCES_DIR, "child_bom_1.json"), Path(cls.RESOURCES_DIR, "child_bom_2.json")]

        # Pass a root bom.json and two sub-project bom.json files in recursive mode.
        with open(os.path.join(cls.EXPECTED_DIR, "deps_artifacts_1.json"), encoding="utf-8") as file:
            # Python dict preserves the order of items, so no need to sort the results.
            expected_result = json.load(file)
            result = convert_components_to_artifacts(
                get_dep_components(root_bom_path=root_bom_path, child_bom_paths=child_bom_paths, recursive=True)
            )
            assert expected_result == result
