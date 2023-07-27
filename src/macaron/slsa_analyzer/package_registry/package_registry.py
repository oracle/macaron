# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines package registries."""

import logging
from abc import ABC, abstractmethod

from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool

logger: logging.Logger = logging.getLogger(__name__)


class PackageRegistry(ABC):
    """Base package registry class."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def load_defaults(self) -> None:
        """Load the .ini configuration for the current package registry."""

    @abstractmethod
    def is_detected(self, build_tool: BaseBuildTool) -> bool:
        """Detect if artifacts of the repo under analysis can possibly be published to this package registry.

        The detection here is based on the repo's detected build tool.
        If the package registry is compatible with the given build tool, it can be a
        possible place where the artifacts produced from the repo are published.

        Parameters
        ----------
        build_tool : BaseBuildTool
            A detected build tool of the repository under analysis.

        Returns
        -------
        bool
            ``True`` if the repo under analysis can be published to this package registry,
            based on the given build tool.
        """
