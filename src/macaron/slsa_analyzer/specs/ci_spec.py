# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildSpec class."""

from typing import TypedDict

from macaron.code_analyzer.call_graph import CallGraph
from macaron.parsers.bashparser import BashCommands
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService


class CIInfo(TypedDict):
    """This class contains the information gathered for a CI service."""

    service: BaseCIService
    """The CI service data."""

    bash_commands: list[BashCommands]
    """List of bash commands triggered by this CI service."""

    callgraph: CallGraph
    """The call graph for this CI service."""

    provenance_assets: list[dict]
    """Release assets for SLSA provenances, e.g., asset for attestation.intoto.jsonl."""

    latest_release: dict
    """The latest release."""

    provenances: list[dict]
    """The SLSA provenances in in-toto format."""
