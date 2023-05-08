# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the repo finder.
"""
import os
from pathlib import Path

from macaron.config.defaults import defaults
from macaron.dependency_analyzer.java_repo_finder import create_urls, parse_gav, parse_pom


def test_java_repo_finder() -> None:
    """Test the functions of the repo finder."""
    gav = "group:artifact:version"
    group, artifact, version = parse_gav(gav)
    assert group != ""
    repositories = defaults.get_list(
        "repofinder", "artifact_repositories", fallback=["https://repo.maven.apache.org/maven2"]
    )
    created_urls = create_urls(group, artifact, version, repositories)
    assert created_urls

    resources_dir = Path(__file__).parent.joinpath("resources")
    with open(os.path.join(resources_dir, "example_pom.xml"), encoding="utf8") as file:
        file_data = file.read()
        found_urls = parse_pom(file_data, ["scm.url", "scm.connection", "scm.developerConnection"])
        expected = [
            "https://github.com/owner/project",
            "ssh://git@hostname:port/owner/project.git",
            "git@github.com:owner/project.git",
        ]
        assert expected == list(found_urls)
