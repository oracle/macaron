# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines the package registries."""

from macaron.slsa_analyzer.package_registry.jfrog_maven_registry import JFrogMavenRegistry
from macaron.slsa_analyzer.package_registry.maven_central_registry import MavenCentralRegistry
from macaron.slsa_analyzer.package_registry.npm_registry import NPMRegistry
from macaron.slsa_analyzer.package_registry.package_registry import PackageRegistry
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIRegistry

PACKAGE_REGISTRIES: list[PackageRegistry] = [
    JFrogMavenRegistry(),
    MavenCentralRegistry(),
    NPMRegistry(),
    PyPIRegistry(),
]
