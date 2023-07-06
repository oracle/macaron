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


class RepoError(MacaronError):
    """Happens when there is an error when preparing the repository for the analysis."""
