# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains Enums used to represent the outcome of Repo Finder or Commit Finder executions."""
from enum import Enum


class RepoFinderOutcome(Enum):
    """An Enum of all outcomes of the Repo Finder being run for a software component."""

    # States that relate to problems with user input.
    NO_MAVEN_HOST_PROVIDED = "No maven host provided"
    NO_POM_TAGS_PROVIDED = "No POM tags provided"
    NO_VERSION_PROVIDED = "No version provided"
    UNSUPPORTED_PACKAGE_TYPE = "Unsupported package type"

    # States that relate to the target POM (Java).
    POM_READ_ERROR = "POM read error"

    # States that relate to the SCM in the POM (Java).
    SCM_NO_URLS = "SCM no URLs"
    SCM_NO_VALID_URLS = "SCM no valid URLs"

    # States that relate to HTTP requests.
    HTTP_INVALID = "HTTP invalid"
    HTTP_NOT_FOUND = "HTTP not found"
    HTTP_FORBIDDEN = "HTTP forbidden"
    HTTP_OTHER = "HTTP other"

    # States that relate to deps.dev (Non-Java).
    DDEV_BAD_RESPONSE = "deps.dev bad response"
    DDEV_JSON_FETCH_ERROR = "deps.dev fetch error"
    DDEV_JSON_INVALID = "deps.dev JSON invalid"
    DDEV_NO_URLS = "deps.dev no URLs"

    # Version related states.
    NO_NEWER_VERSION = "No newer version than provided which failed"

    # Success states.
    FOUND = "Found"
    FOUND_FROM_PARENT = "Found from parent"
    FOUND_FROM_LATEST = "Found form latest"

    # Default state.
    NOT_USED = "Not used"


class CommitFinderOutcome(Enum):
    """An Enum of all outcomes of the Commit Finder being run for a software component."""

    # States that relate to problems with user input.
    NO_VERSION_PROVIDED = "No version provided"
    UNSUPPORTED_PURL_TYPE = "Unsupported PURL type"

    # States that relate to repository type PURLs.
    REPO_PURL_FAILURE = "Repository PURL failure"

    # States that relate to artifact type PURLs.
    NO_TAGS = "No tags"
    NO_TAGS_WITH_COMMITS = "No tags with commits"
    NO_TAG_COMMIT = "No tag commit"
    INVALID_PURL = "No valid parts"
    REGEX_COMPILE_FAILURE = "Regex compile failure"
    NO_TAGS_MATCHED = "No tags matched"

    # Success state.
    MATCHED = "Matched"

    # Default state.
    NOT_USED = "Not used"
