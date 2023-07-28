# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the python dd repo finder.
"""
from macaron.repo_finder.repo_finder_dd import RepoFinderDD


def test_repo_finder_dd() -> None:
    """Test the functions of the repo finder."""
    repo_finder = RepoFinderDD("pypi")
    assert (
        repo_finder.create_type_specific_url("", "packageurl-python")
        == "https://api.deps.dev/v3alpha/systems/pypi/packages/packageurl-python"
    )
