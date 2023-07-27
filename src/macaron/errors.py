# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
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


class DuplicateError(MacaronError):
    """The class for errors for duplicated data."""


class ProvenanceLoadError(MacaronError):
    """Happens when there is an issue decoding and loading a provenance from a provenance asset."""
