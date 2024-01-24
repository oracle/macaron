# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module handles in-toto version 1 attestations."""

from typing import TypedDict


class InTotoV1Statement(TypedDict):
    """An in-toto version 1 statement.

    This is the type of the payload in a version 1 in-toto attestation.
    Specification: https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md.
    """
