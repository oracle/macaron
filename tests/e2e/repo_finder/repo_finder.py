#!/usr/bin/env python3

# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the functionality of the repo finder's remote API calls."""

import logging
import os

from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.repo_finder.repo_finder import find_repo

logger: logging.Logger = logging.getLogger(__name__)

# Set logging debug level.
logger.setLevel(logging.DEBUG)


def test_repo_finder() -> int:
    """Test the functionality of the remote API calls used by the repo finder.

    Functionality relating to Java artifacts is not verified for two reasons:
    - It is extremely unlikely that Maven central will change its API or cease operation in the near future.
    - Other similar repositories to Maven central (internal Artifactory, etc.) can be provided by the user instead.
    """
    defaults.add_section("repofinder")
    defaults.set("repofinder", "use_open_source_insights", "True")

    defaults.add_section("git_service.github")
    defaults.set("git_service.github", "domain", "github.com")

    defaults.add_section("git_service.gitlab")
    defaults.set("git_service.gitlab", "domain", "gitlab.com")

    # Test deps.dev API for a Python package.
    if not find_repo(PackageURL.from_string("pkg:pypi/packageurl-python@0.11.1")):
        return os.EX_UNAVAILABLE

    # Test deps.dev API for a Nuget package.
    if not find_repo(PackageURL.from_string("pkg:nuget/azure.core")):
        return os.EX_UNAVAILABLE

    # Test deps.dev API for an NPM package.
    if not find_repo(PackageURL.from_string("pkg:npm/@colors/colors")):
        return os.EX_UNAVAILABLE

    # Test deps.dev API for Cargo package.
    if not find_repo(PackageURL.from_string("pkg:cargo/rand_core")):
        return os.EX_UNAVAILABLE

    return os.EX_OK


if __name__ == "__main__":
    test_repo_finder()
