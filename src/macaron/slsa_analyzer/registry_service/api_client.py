# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides API clients for Registry services, such as PyPi."""

import logging

from macaron.util import send_get_http

logger: logging.Logger = logging.getLogger(__name__)

# TODO: Create BaseAPIClient


class PyPIAPIClient:
    """This class acts as a client to use PyPi API.

    See https://warehouse.pypa.io/api-reference/ for the PyPI API documentation.
    """

    _PYPI_API_URL = "https://pypi.org/pypi"

    def get_all_project_data(self, project_name: str) -> dict:
        """Query PyPi JSON API for the information about an individual project at the latest version.

        The url would be in the following form:
        ``https://pypi.org/pypi/{project_name}/json``

        Parameters
        ----------
        project_name : str
            The full name of the project (case insensitive).

        Returns
        -------
        dict
            The json query result or an empty dict if failed.

        Examples
        --------
        The following call to this method will perform a query to ``https://pypi.org/pypi/flask/json``

        >>> pypi_client.get_all_project_data(
            project_name="flask"
        )
        """
        logger.debug("Query for project %s 's data", project_name)
        url = f"{PyPIAPIClient._PYPI_API_URL}/{project_name}/json"
        response_data = send_get_http(url, {})
        return response_data

    def get_release_data(self, project_name: str, version: str) -> dict:
        """Query PyPi JSON API for the information about an individual release at a specific version.

        The url would be in the following form:
        ``https://pypi.org/pypi/{project_name}/{version}/json``

        Parameters
        ----------
        project_name : str
            The full name of the project (case insensitive).
        version : str
            The version of the project in the form ``*.*.*``.

        Returns
        -------
        dict
            The json query result or an empty dict if failed.

        Examples
        --------
        The following call to this method will perform a query to ``https://pypi.org/pypi/flask/1.0.0/json``

        >>> pypi_client.get_release_data(
            project_name="flask",
            version="1.0.0"
        )
        """
        logger.debug("Query for project %s 's data at version %s", project_name, version)
        url = f"{PyPIAPIClient._PYPI_API_URL}/{project_name}/{version}/json"
        response_data = send_get_http(url, {})
        return response_data
