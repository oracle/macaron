# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This package contains the dependency resolvers for Java projects."""

from .cyclonedx_mvn import CycloneDxMaven  # noqa: F401
from .dependency_resolver import DependencyAnalyzer, DependencyInfo, DependencyTools  # noqa: F401
