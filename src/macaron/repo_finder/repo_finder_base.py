# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the base class for the repo finders."""

from abc import ABC, abstractmethod

from packageurl import PackageURL

from macaron.repo_finder.repo_finder_enums import RepoFinderOutcome


class BaseRepoFinder(ABC):
    """This abstract class is used to represent Repository Finders."""

    @abstractmethod
    def find_repo(self, purl: PackageURL) -> tuple[str, RepoFinderOutcome]:
        """
        Generate iterator from _find_repo that attempts to retrieve a repository URL that matches the passed artifact.

        Parameters
        ----------
        purl : PackageURL
            The PURL of an artifact.

        Returns
        -------
        tuple[str, RepoFinderOutcome] :
            A tuple of the found URL (or an empty string), and the outcome of the Repo Finder.
        """
