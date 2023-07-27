# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.


"""This module contains data related to one package registry that is matched against a repository."""

from dataclasses import dataclass, field

from macaron.slsa_analyzer.asset import Asset
from macaron.slsa_analyzer.build_tool import BaseBuildTool
from macaron.slsa_analyzer.package_registry import PackageRegistry
from macaron.util import JsonType


@dataclass
class PackageRegistryData:
    """This class contains data for one package registry that is matched against a repository.

    Attributes
    ----------
    build_tool : BaseBuildTool
        The build tool matched against the repository.

    package_registry : PackageRegistry
        The package registry matched against the repository. This is dependent on the build tool detected.

    latest_version : str | None
        The latest version of the artifact found on the registry.

    provenance_assets : list[dict]
        Release assets for SLSA provenances, e.g., asset for attestation.intoto.jsonl.
        Each entry of the list is a dictionary with two keys: ``"name"`` - the name of the
        provenance file, and ``"url"`` - the URL where the provenance can be retrieved.

    provenances : dict[str, dict]
        The JSON payloads of the SLSA provenances matched against the current repo, in
        in-toto format.
        Each key is the URL to where the provenance file is hosted and each value is the
        JSON payload of the corresponding provenance.
    """

    build_tool: BaseBuildTool
    package_registry: PackageRegistry
    latest_version: str | None = None
    provenance_assets: list[Asset] = field(default_factory=list)
    provenances: dict[str, JsonType] = field(default_factory=dict)
