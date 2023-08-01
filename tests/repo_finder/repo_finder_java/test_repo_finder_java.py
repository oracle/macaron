# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the repo finder.
"""
import os
from pathlib import Path

from macaron.repo_finder.repo_finder_java import JavaRepoFinder


def test_java_repo_finder() -> None:
    """Test the functions of the repo finder."""
    group = "group"
    artifact = "artifact"
    version = "version"
    repo_finder = JavaRepoFinder()
    created_urls = repo_finder.create_urls(group, artifact, version)
    assert created_urls

    resources_dir = Path(__file__).parent.joinpath("resources")
    with open(os.path.join(resources_dir, "example_pom.xml"), encoding="utf8") as file:
        file_data = file.read()
        pom = repo_finder.parse_pom(file_data)
        assert pom is not None
        found_urls = repo_finder.find_scm(
            pom, ["scm.url", "scm.connection", "scm.developerConnection", "licenses.license.distribution"]
        )
        assert len(found_urls) == 4
        expected = [
            "https://github.com/owner/project",
            "ssh://git@hostname:port/owner/Example_License.git",
            "git@github.com:owner/project1.8-2023.git",
            "${licenses.license.distribution}",
        ]
        assert expected == found_urls


def test_java_repo_finder_hierarchical() -> None:
    """Test the hierarchical capabilities of the repo finder."""
    resources_dir = Path(__file__).parent.joinpath("resources")
    repo_finder = JavaRepoFinder()
    with open(os.path.join(resources_dir, "example_pom_no_scm.xml"), encoding="utf8") as file:
        file_data = file.read()
        pom = repo_finder.parse_pom(file_data)
        assert pom is not None
        group, artifact, version = repo_finder.find_parent(pom)
        assert group == "owner"
        assert artifact == "parent"
        assert version == "1"
