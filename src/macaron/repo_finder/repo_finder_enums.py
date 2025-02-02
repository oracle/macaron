# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains Enums used to represent the outcome of Repo Finder or Commit Finder executions."""
from enum import Enum


class RepoFinderInfo(Enum):
    """An Enum providing information on the outcomes of the Repo Finder being run for a software component."""

    #: Reported if the URL that serves requested Maven packages is not provided by the user in Macaron's config.
    #: E.g. Maven central.
    NO_MAVEN_HOST_PROVIDED = "No maven host provided"

    #: Reported if the list of period separated tags that point to the SCM within the POM is not provided by the user in
    #: Macaron's config. E.g. scm.url, scm.connection
    NO_POM_TAGS_PROVIDED = "No POM tags provided"

    #: Reported if the user does not provide a version for the Repo Finder via the command line, and does not allow the
    #: version to be automatically discovered.
    NO_VERSION_PROVIDED = "No version provided"

    #: Reported if the user provides an unsupported type in the PURL command line argument.
    UNSUPPORTED_PACKAGE_TYPE = "Unsupported package type"

    #: Reported if there was an error reading the POM file.
    POM_READ_ERROR = "POM read error"

    #: Reported if the POM file contains no URLs within the SCM found at the provided tag locations.
    SCM_NO_URLS = "SCM no URLs"

    #: Reported if the POM file contains no VALID URLs within the SCM found at the provided tag locations. Validity is
    #: defined as any URL that resolves to a recognised version control system.
    SCM_NO_VALID_URLS = "SCM no valid URLs"

    #: Reported if the URL of the repository could not be reached.
    HTTP_INVALID = "HTTP invalid"

    #: Reported if the URL host returns a 404 (not found) for the sought resource.
    HTTP_NOT_FOUND = "HTTP not found"

    #: Reported if the URL host returns a 403 (forbidden) for the sought resource.
    HTTP_FORBIDDEN = "HTTP forbidden"

    #: Reported for all other bad status codes that a host could return. E.g. 500, etc.
    HTTP_OTHER = "HTTP other"

    #: Reported if deps.dev produces no response to the HTTP request.
    DDEV_BAD_RESPONSE = "deps.dev bad response"

    #: Reported if deps.dev returns JSON data that cannot be parsed.
    DDEV_JSON_FETCH_ERROR = "deps.dev fetch error"

    #: Reported if deps.dev returns JSON data that is missing expected fields.
    DDEV_JSON_INVALID = "deps.dev JSON invalid"

    #: Reported if deps.dev returns data that does not contain the desired SCM URL. E.g. The repository URL.
    DDEV_NO_URLS = "deps.dev no URLs"

    #: Reported if the provided PURL did not produce a result, but a more recent version could not be found.
    NO_NEWER_VERSION = "No newer version than provided which failed"

    #: Reported if the provided PURL did not produce a result, and the most recent version also failed.
    LATEST_VERSION_INVALID = "A newer version than provided also failed"

    #: Reported when a repository is found.
    FOUND = "Found"

    #: Reported when a repository is found via a parent POM.
    FOUND_FROM_PARENT = "Found from parent"

    #: Reported when a repository is found from a more recent version than was provided by the user.
    FOUND_FROM_LATEST = "Found form latest"

    #: Default value. Reported if the Repo Finder was not called. E.g. Because the repository URL was already present.
    NOT_USED = "Not used"


class CommitFinderInfo(Enum):
    """An Enum providing information on the outcomes of the Commit Finder being run for a software component."""

    #: Reported if the user does not provide a version for the Repo Finder via the command line, and does not allow the
    #: version to be automatically discovered.
    NO_VERSION_PROVIDED = "No version provided"

    #: Reported if the user provides an unsupported type in the PURL command line argument.
    UNSUPPORTED_PURL_TYPE = "Unsupported PURL type"

    #: Reported if the user provided a repository type PURL with the tag or commit in the version, but neither were
    #: valid.
    REPO_PURL_FAILURE = "Repository PURL failure"

    #: Reported if the repository has no Git tags.
    NO_TAGS = "No Git tags"

    #: Reported if the repository has no Git tags with associated commits.
    NO_TAGS_WITH_COMMITS = "No Git tags with commits"

    #: Reported if the tag selected from the repository fails to resolve to a commit despite having one associated with
    # it.
    NO_TAG_COMMIT = "No valid commit found for Git tag"

    #: Reported if the version part of the user provided PURL is invalid.
    INVALID_VERSION = "No valid version parts in PURL"

    #: Reported if the Regex pattern to be created from parts of the user provided PURL fails to compile.
    REGEX_COMPILE_FAILURE = "Regex compile failure"

    #: Reported if no tags from the Git repository could be matched to the sought version.
    NO_TAGS_MATCHED = "No Git tags matched"

    #: Reported if a match was found.
    MATCHED = "Matched"

    #: Default state. Reported if the commit finder was not called. E.g. Because the Repo Finder failed.
    NOT_USED = "Not used"
