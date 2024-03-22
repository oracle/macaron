# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the repo finder."""
import os
from pathlib import Path

import pytest

from macaron.config.defaults import load_defaults
from macaron.repo_finder.repo_finder_java import JavaRepoFinder


@pytest.mark.parametrize(
    ("user_config_input", "expected"),
    [
        (
            """
                [repofinder.java]
                repo_pom_paths =
                    scm.connection
                    scm.url
            """,
            ["scm:git:git@github.com:oracle-samples/macaron.git", "https://github.com/oracle/macaron"],
        ),
        (
            """
                [repofinder.java]
                repo_pom_paths =
                    scm.url
                    scm.connection
            """,
            ["https://github.com/oracle/macaron", "scm:git:git@github.com:oracle-samples/macaron.git"],
        ),
    ],
)
def test_pom_extraction_ordering(tmp_path: Path, user_config_input: str, expected: list[str]) -> None:
    """Test the ordering of elements extracted from the POM is correct and maintained."""
    pom_text = """
    <project>
        <url>https://example.org</url>
        <scm>
            <connection>scm:git:git@github.com:oracle-samples/macaron.git</connection>
            <url>https://github.com/oracle/macaron</url>
        </scm>
        <properties>
            <url>1.9.15</url>
        </properties>
    </project>
    """
    user_config_path = os.path.join(tmp_path, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as user_config_file:
        user_config_file.write(user_config_input)
    load_defaults(user_config_path)

    repo_finder = JavaRepoFinder()

    # Retrieve SCM from POM.
    assert expected == repo_finder._read_pom(pom_text)  # pylint: disable=W0212
