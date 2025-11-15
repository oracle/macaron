# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.


"""This module contains data related to one package registry that is matched against a repository."""

from dataclasses import dataclass, field

from macaron.slsa_analyzer.asset import AssetLocator
from macaron.slsa_analyzer.package_registry import PackageRegistry
from macaron.slsa_analyzer.provenance.provenance import DownloadedProvenanceData


@dataclass
class PackageRegistryInfo:
    """This class contains data for one package registry that is matched against a software component."""

    #: The purl type of the build tool matched against the repository.
    ecosystem: str
    #: The package registry matched against the repository. This is dependent on the build tool detected.
    package_registry: PackageRegistry
    #: The provenances matched against the current repo.
    provenances: list[DownloadedProvenanceData] = field(default_factory=list)
    #: The metadata obtained by the registry.
    metadata: list[AssetLocator] = field(default_factory=list)
