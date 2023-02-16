# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This package contains the dependency resolvers for Java projects."""

from .dependency_resolver import (  # noqa: F401
    DependencyAnalyzer,
    DependencyAnalyzerError,
    DependencyInfo,
    DependencyTools,
    NoneDependencyAnalyzer,
)
