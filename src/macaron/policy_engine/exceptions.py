# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Exceptions used by the policy engine."""


from macaron.errors import MacaronError


class InvalidPolicyError(MacaronError):
    """Happens when the policy is invalid."""


class PolicyRuntimeError(MacaronError):
    """Happens if there are errors while validating the policy against a target."""


class CUEPolicyError(MacaronError):
    """Happens when the CUE policy is invalid."""


class CUERuntimeError(MacaronError):
    """Happens when there are errors in CUE policy validation."""
