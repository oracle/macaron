# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the base class for the repo finders."""

from abc import ABC, abstractmethod
from collections.abc import Iterator

from packageurl import PackageURL


class BaseRepoFinder(ABC):
    """This abstract class is used to represent Repository Finders."""

    @abstractmethod
    def find_repo(self, purl: PackageURL) -> Iterator:
        """
        Generate iterator from _find_repo that attempts to retrieve a repository URL that matches the passed artifact.

        Parameters
        ----------
        purl : PackageURL
            The PURL of an artifact.

        Yields
        ------
        Iterator :
            An iterator that produces the found URLs.
        """
