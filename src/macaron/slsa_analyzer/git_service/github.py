# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for the GitHub service."""

from macaron.config.global_config import global_config
from macaron.errors import ConfigurationError
from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.git_service.api_client import GhAPIClient, get_default_gh_client
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService


class GitHub(BaseGitService):
    """This class contains the spec of the GitHub service."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__("github")
        self._api_client: GhAPIClient | None = None

    def load_defaults(self) -> None:
        """Load the values for this git service from the ini configuration and environment variables.

        Raises
        ------
        ConfigurationError
            If there is an error loading the configuration.
        """
        try:
            self.domain = self.load_domain(section_name="git_service.github")
        except ConfigurationError as error:
            raise error

    @property
    def api_client(self) -> GhAPIClient:
        """Return the API client used for querying GitHub API.

        This API is used to check if a GitHub repo can be cloned.
        """
        if not self._api_client:
            self._api_client = get_default_gh_client(global_config.gh_token)

        return self._api_client

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
        remote_url = git_url.get_remote_vcs_url(url)
        full_name = git_url.get_repo_full_name_from_url(remote_url)
        if not self.api_client.get_repo_data(full_name):
            return False

        return True

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
