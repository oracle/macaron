# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for the BitBucket service."""

import logging

from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService

logger: logging.Logger = logging.getLogger(__name__)


class BitBucket(BaseGitService):
    """This class contains the spec of the BitBucket service."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__("bitbucket")

    def load_defaults(self) -> None:
        """Load the values for this git service from the ini configuration."""
        return None

    def can_clone_remote_repo(self, url: str) -> bool:
        """Return True if the remote repository can be cloned.

        Parameters
        ----------
        url : str
            The remote url.

        Returns
        -------
        bool
            True if the repo can be cloned, else False.
        """
        logger.info("Cloning BitBucket repositories is not supported yet. Please clone the repository manually.")
        return False

    def is_detected(self, url: str) -> bool:
        """Return True if the remote repo is using this git service.

        Parameters
        ----------
        url : str
            The url of the remote repo.

        Returns
        -------
        bool
            True if this git service is detected else False.
        """
        parsed_url = git_url.parse_remote_url(url)
        if not parsed_url or self.name not in parsed_url.netloc:
            return False

        return True
