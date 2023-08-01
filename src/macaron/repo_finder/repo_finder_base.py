# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the base class for the repo finders."""

from abc import ABC, abstractmethod
from collections.abc import Iterator

import requests


class BaseRepoFinder(ABC):
    """This abstract class is used to represent Repository Finders."""

    @abstractmethod
    def find_repo(self, group: str, artifact: str, version: str) -> Iterator[str]:
        """
        Attempt to retrieve a repository URL that matches the passed artifact.

        Parameters
        ----------
        group : str
            The group identifier of an artifact.
        artifact : str
            The artifact name of an artifact.
        version : str
            The version number of an artifact.

        Yields
        ------
        Iterator[str] :
            The URLs found for the passed GAV.
        """

    @abstractmethod
    def create_urls(self, group: str, artifact: str, version: str) -> list[str]:
        """
        Create the urls to search for the metadata relating to the passed artifact.

        Parameters
        ----------
        group : str
            The group ID.
        artifact: str
            The artifact ID.
        version: str
            The version of the artifact.

        Returns
        -------
        list[str]
            The list of created URLs.
        """

    @abstractmethod
    def retrieve_metadata(self, session: requests.Session, url: str) -> str:
        """
        Attempt to retrieve the file located at the passed URL using the passed Session.

        Parameters
        ----------
        session : requests.Session
            The HTTP session to use for attempting the GET request.
        url : str
            The URL for the GET request.

        Returns
        -------
        str :
            The retrieved file data or an empty string.
        """

    @abstractmethod
    def read_metadata(self, metadata: str) -> list[str]:
        """
        Parse the passed metadata and extract the relevant information.

        Parameters
        ----------
        metadata : str
            The metadata as a string.

        Returns
        -------
        list[str] :
            The extracted contents as a list of strings.
        """
