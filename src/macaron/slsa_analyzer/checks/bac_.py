# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains a class to store results from the BuildAsCodeCheck subchecks."""
from attr import dataclass


@dataclass
class BuildAsCodeSubchecks:
    """Dataclass for storing the results from the BuildAsCodeCheck subchecks."""

    ci_parsed: float
    deploy_action: float
    deploy_command: float
    deploy_kws: float


build_as_code_subchecks: BuildAsCodeSubchecks = None  # type: ignore # pylint: disable=invalid-name
