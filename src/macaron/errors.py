# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains error classes for Macaron."""


class MacaronError(Exception):
    """The base class for Macaron errors."""


class InvalidExpectationError(MacaronError):
    """Happens when the provenance expectation is invalid."""


class ExpectationRuntimeError(MacaronError):
    """Happens if there are errors while validating the expectation against a target."""


class CUEExpectationError(MacaronError):
    """Happens when the CUE expectation is invalid."""


class CUERuntimeError(MacaronError):
    """Happens when there are errors in CUE expectation validation."""


class ConfigurationError(MacaronError):
    """Happens when there is an error in the configuration (.ini) file."""


class CloneError(MacaronError):
    """Happens when cannot clone a git repository."""


class RepoCheckOutError(MacaronError):
    """Happens when there is an error when checking out the correct revision of a git repository."""


class RepoNotFoundError(MacaronError):
    """Happens if a repository is not found."""


class PURLNotFoundError(MacaronError):
    """Happens if the PURL identifier for a software component is not found."""


class InvalidPURLError(MacaronError):
    """Happens when the input PURL string is invalid."""


class DuplicateError(MacaronError):
    """The class for errors for duplicated data."""


class InvalidHTTPResponseError(MacaronError):
    """Happens when the HTTP response is invalid or unexpected."""


class CheckRegistryError(MacaronError):
    """The Check Registry Error class."""


class ProvenanceError(MacaronError):
    """When there is an error while extracting from provenance."""


class JsonError(MacaronError):
    """When there is an error while extracting from JSON."""


class InvalidAnalysisTargetError(MacaronError):
    """When a valid Analysis Target cannot be constructed."""


class ParseError(MacaronError):
    """The errors related to parsers."""


class CallGraphError(MacaronError):
    """The errors related to callgraphs."""


class GitHubActionsValueError(MacaronError):
    """The errors related to GitHub Actions value errors."""
