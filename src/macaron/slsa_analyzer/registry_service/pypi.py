# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for the PyPI service."""

from macaron.slsa_analyzer.registry_service.api_client import PyPIAPIClient


class PyPI:
    """This class contains the spec of the PyPI service."""

    def __init__(self) -> None:
        """Initialize instance."""
        self._api_client: PyPIAPIClient = None  # type: ignore

    @property
    def api_client(self) -> PyPIAPIClient:
        """Return the API client used for querying PyPI API.

        This API is used to check if a PyPI repo can be cloned.
        """
        if not self._api_client:
            self._api_client = PyPIAPIClient()

        return self._api_client
