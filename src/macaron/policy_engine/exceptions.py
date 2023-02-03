# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Exceptions used by the policy engine."""


class InvalidPolicyError(Exception):
    """Happen when the policy is invalid."""


class PolicyRuntimeError(Exception):
    """Happen if there are errors while validating the policy against a target."""
