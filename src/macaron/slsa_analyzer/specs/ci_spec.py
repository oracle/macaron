# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildSpec class."""

from typing import TypedDict

from macaron.code_analyzer.call_graph import CallGraph
from macaron.parsers.bashparser import BashCommands
from macaron.slsa_analyzer.asset import AssetLocator
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService


class CIInfo(TypedDict):
    """This class contains the information gathered for a CI service."""

    service: BaseCIService
    """The CI service data."""

    bash_commands: list[BashCommands]
    """List of bash commands triggered by this CI service."""

    callgraph: CallGraph
    """The call graph for this CI service."""

    provenance_assets: list[AssetLocator]
    """Release assets for SLSA provenances, e.g., asset for attestation.intoto.jsonl.

    For GitHub Actions, each asset is a member of the ``assets`` list in the GitHub
    Actions latest release payload.
    See: https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28#get-the-latest-release.
    """

    latest_release: dict
    """The latest release.
    Schema: https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28#get-the-latest-release.
    """

    provenances: list[dict]
    """The JSON payloads of SLSA provenances in in-toto format."""
