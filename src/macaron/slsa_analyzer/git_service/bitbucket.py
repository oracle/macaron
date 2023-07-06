# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for the BitBucket service."""

import logging

from pydriller.git import Git

from macaron.errors import RepoError
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService

logger: logging.Logger = logging.getLogger(__name__)


class BitBucket(BaseGitService):
    """This class contains the spec of the BitBucket service."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__("bitbucket")

    def load_defaults(self) -> None:
        """Load the values for this git service from the ini configuration."""
        # TODO: implement this once support for BitBucket is added.
        return None

    def clone_repo(self, _clone_dir: str, _url: str) -> None:
        """Clone a BitBucket repo."""
        # TODO: implement this once support for BitBucket is added.
        logger.info("Cloning BitBucket repositories is not supported yet. Please clone the repository manually.")

    def check_out_repo(self, git_obj: Git, branch: str, digest: str, offline_mode: bool) -> Git:
        """Checkout the branch and commit specified by the user of a repository."""
        raise RepoError("Checking out a branch or commit on a Bitbucket repository is not supported yet.")
