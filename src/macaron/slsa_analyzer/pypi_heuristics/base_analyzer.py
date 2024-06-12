# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Define and initialize the base analyzer."""

from macaron.slsa_analyzer.pypi_heuristics.analysis_result import RESULT
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC


class BaseAnalyzer:
    """The base analyzer initialization."""

    def __init__(
        self,
        name: str = "",
        heuristic: HEURISTIC | None = None,
        depends_on: list[tuple] | None = None,
    ) -> None:
        self.name: str = name
        self.heuristic: HEURISTIC | None = heuristic
        self.depends_on: list[
            tuple[HEURISTIC, RESULT]
        ] | None = depends_on  # Contains the dependent heuristics and the expected result of each heuristic

    def analyze(self) -> tuple[RESULT, dict]:
        """Implement the base analyze method for seven analyzers."""
        return RESULT.SKIP, {}
