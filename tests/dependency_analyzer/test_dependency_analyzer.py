# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the DependencyAnalyzer.
"""

from pathlib import Path

from macaron.config.target_config import TARGET_CONFIG_SCHEMA, Configuration
from macaron.dependency_analyzer import DependencyAnalyzer
from macaron.dependency_analyzer.dependency_resolver import DependencyInfo
from macaron.output_reporter.results import SCMStatus
from macaron.parsers.yaml.loader import YamlLoader
from tests.macaron_testcase import MacaronTestCase


class TestDependencyAnalyzer(MacaronTestCase):
    """Test the dependency analyzer functions."""

    CONFIG_DIR = Path(__file__).parent.joinpath("configurations")

    def test_merge_config(self) -> None:
        """Test merging the manual and automatically resolved configurations."""
        # Mock automatically resolved dependencies.
        auto_deps = {
            "com.fasterxml.jackson.core:jackson-annotations": DependencyInfo(
                version="2.14.0-SNAPSHOT",
                group="com.fasterxml.jackson.core",
                name="jackson-annotations",
                url="https://github.com/FasterXML/jackson-annotations",
                note="",
                available=SCMStatus.AVAILABLE,
            ),
            "com.fasterxml.jackson.core:jackson-core": DependencyInfo(
                version="2.14.0-SNAPSHOT",
                group="com.fasterxml.jackson.core",
                name="jackson-core",
                url="https://github.com/FasterXML/jackson-core",
                note="",
                available=SCMStatus.AVAILABLE,
            ),
        }

        # Define expected results.
        expected_result_no_deps = [
            {
                "id": "com.fasterxml.jackson.core:jackson-annotations",
                "path": "https://github.com/FasterXML/jackson-annotations",
                "branch": "",
                "digest": "",
                "note": "",
                "available": SCMStatus.AVAILABLE,
            },
            {
                "id": "com.fasterxml.jackson.core:jackson-core",
                "path": "https://github.com/FasterXML/jackson-core",
                "branch": "",
                "digest": "",
                "note": "",
                "available": SCMStatus.AVAILABLE,
            },
        ]

        expected_result_with_deps = [
            {
                "id": "id",
                "path": "https://github.com/owner/name.git",
                "branch": "master",
                "digest": "aac3b3bcb608e1e8451d4beedd38ecbe6306e7e7",
                "note": "",
                "available": SCMStatus.AVAILABLE,
            },
            {
                "id": "id",
                "path": "https://github.com/owner/name_2.git",
                "branch": "master",
                "digest": "aac3b3bcb608e1e8451d4beedd38ecbe6306e7e7",
                "note": "",
                "available": SCMStatus.AVAILABLE,
            },
            {
                "id": "com.fasterxml.jackson.core:jackson-annotations",
                "path": "https://github.com/FasterXML/jackson-annotations",
                "branch": "",
                "digest": "",
                "note": "",
                "available": SCMStatus.AVAILABLE,
            },
            {
                "id": "com.fasterxml.jackson.core:jackson-core",
                "path": "https://github.com/FasterXML/jackson-core",
                "branch": "",
                "digest": "",
                "note": "",
                "available": SCMStatus.AVAILABLE,
            },
        ]

        # Get the mock config file with dependencies.
        path = self.CONFIG_DIR.joinpath("valid_has_deps.yaml")
        user_config = YamlLoader.load(path, TARGET_CONFIG_SCHEMA)
        user_dep_config = [Configuration(dep) for dep in user_config.get("dependencies", [])]
        merged_configs = DependencyAnalyzer.merge_configs(user_dep_config, auto_deps)

        assert [dep.options for dep in merged_configs] == expected_result_with_deps

        # Get the mock config file without dependencies.
        path = self.CONFIG_DIR.joinpath("valid_no_deps.yaml")
        user_config = YamlLoader.load(path, TARGET_CONFIG_SCHEMA)
        merged_configs = DependencyAnalyzer.merge_configs(user_config.get("dependencies"), auto_deps)

        assert [dep.options for dep in merged_configs] == expected_result_no_deps

    def test_tool_valid(self) -> None:
        """Test the tool name and version is valid."""
        assert DependencyAnalyzer.tool_valid("cyclonedx:2.6.2") is False
        assert DependencyAnalyzer.tool_valid("cyclonedx-maven:2.6.2") is True
        assert DependencyAnalyzer.tool_valid("cyclonedx-maven:abc") is False
