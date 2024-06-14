# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Define and initialize the base analyzer."""

from abc import abstractmethod

from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIRegistry
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import HeuristicResult
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC


class BaseHeuristicAnalyzer:
    """The base analyzer initialization."""

    def __init__(
        self,
        name: str,
        heuristic: HEURISTIC,
        depends_on: list[tuple[HEURISTIC, HeuristicResult]] | None,
    ) -> None:
        self.name: str = name
        self.heuristic: HEURISTIC = heuristic
        self.depends_on: list[
            tuple[HEURISTIC, HeuristicResult]
        ] | None = depends_on  # Contains the dependent heuristics and the expected result of each heuristic

    @abstractmethod
    def analyze(self, api_client: PyPIRegistry) -> tuple[HeuristicResult, dict]:
        """
        Implement the base analyze method for seven analyzers.

        Returns
        -------
            tuple[HeuristicResult, int | dict]: Contain the heuristic result and the metadata of the package.
            E.g. (1) The release frequency (2) {"maintainers_join_date": datetime}
        """
        raise NotImplementedError
