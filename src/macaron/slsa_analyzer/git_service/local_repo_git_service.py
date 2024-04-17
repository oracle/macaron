# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for the local repo git service."""

import logging

from pydriller.git import Git

from macaron.errors import ConfigurationError, RepoCheckOutError
from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService

logger: logging.Logger = logging.getLogger(__name__)


class LocalRepoGitService(BaseGitService):
    """This class contains the spec of the local repo git service."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__("local_repo")

    def load_defaults(self) -> None:
        """Load the values for this git service from the ini configuration."""
        try:
            self.hostname = self.load_hostname(section_name="git_service.local_repo")
        except ConfigurationError as error:
            raise error

    def clone_repo(self, _clone_dir: str, _url: str) -> None:
        """Cloning from a local repo git service is not supported."""
        raise NotImplementedError

    def check_out_repo(self, git_obj: Git, branch: str, digest: str, offline_mode: bool) -> Git:
        """Checkout the branch and commit specified by the user of a repository."""
        if not git_url.check_out_repo_target(git_obj, branch, digest, offline_mode):
            raise RepoCheckOutError(
                f"Failed to check out branch {branch} and commit {digest} for repo {git_obj.project_name}."
            )

        return git_obj
