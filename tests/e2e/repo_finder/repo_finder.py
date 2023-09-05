#!/usr/bin/env python3

# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the functionality of the repo finder's remote API calls."""

import logging
import os

from macaron.repo_finder.repo_finder_deps_dev import RepoFinderDepsDev

logger: logging.Logger = logging.getLogger(__name__)

# Set logging debug level.
logger.setLevel(logging.DEBUG)


def test_repo_finder() -> int:
    """Test the functionality of the remote API calls used by the repo finder.

    Functionality relating to Java artifacts is not verified for two reasons:
    - It is extremely unlikely that Maven central will change its API or cease operation in the near future.
    - Other similar repositories to Maven central (internal Artifactory, etc.) can be provided by the user instead.
    """
    # Test deps.dev API for a Python package
    repo_finder = RepoFinderDepsDev("pypi")
    urls = []
    # Without version
    urls.append(repo_finder.create_urls("", "packageurl-python", ""))
    # With version
    urls.append(repo_finder.create_urls("", "packageurl-python", "0.11.1"))
    for url in urls:
        logger.debug("Testing: %s", url[0])
        metadata = repo_finder.retrieve_metadata(url[0])
        if not metadata:
            return os.EX_UNAVAILABLE
        links = repo_finder.read_metadata(metadata)
        if not links:
            return os.EX_UNAVAILABLE
    return os.EX_OK


if __name__ == "__main__":
    test_repo_finder()
