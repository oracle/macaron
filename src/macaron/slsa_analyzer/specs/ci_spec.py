# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildSpec class."""

from collections.abc import Sequence
from typing import TypedDict

from macaron.code_analyzer.call_graph import CallGraph
from macaron.slsa_analyzer.asset import AssetLocator
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload
from macaron.slsa_analyzer.provenance.provenance import DownloadedProvenanceData


class CIInfo(TypedDict):
    """This class contains the information gathered for a CI service."""

    service: BaseCIService
    """The CI service data."""

    callgraph: CallGraph
    """The call graph for this CI service."""

    provenance_assets: list[AssetLocator]
    """Release assets for provenances, e.g., asset for attestation.intoto.jsonl.

    For GitHub Actions, each asset is a member of the ``assets`` list in the GitHub
    Actions appropriate release payload.
    See: https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28#get-a-release-by-tag-name.
    """

    release: dict
    """The appropriate release.
    Schema: https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28#get-a-release-by-tag-name
    """

    provenances: Sequence[DownloadedProvenanceData]
    """The provenances data."""

    build_info_results: InTotoV01Payload
    """The build information results computed for a build step. We use the in-toto 0.1 as the spec."""
