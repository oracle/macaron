# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for the GitLab service.

Note: We are making the assumption that we are only supporting two different GitLab
services: one is called ``public`` and the other is called ``private``.

The corresponding access tokens are stored in the environment variables
``MCN_PUBLIC_GITLAB_TOKEN`` and ``MCN_PRIVATE_GITLAB_TOKEN``, respectively.

Reason for this is mostly because of our assumption that Macaron is used as a
container. Fixing static names for the environment variables allows for easier
propagation of these variables into the container.

In the ini configuration file, settings for the ``public`` GitLab service is in the
``[git_service.gitlab.public]`` section; settings for the ``private`` GitLab service
is in the ``[git_service.gitlab.private]`` section.
"""

import os
from abc import abstractmethod

from macaron.errors import ConfigurationError
from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService


class GitLab(BaseGitService):
    """This class contains the spec of the GitLab service."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__("gitlab")
        self.access_token: str | None = None

    @abstractmethod
    def load_defaults(self) -> None:
        """Load the .ini configuration."""
        raise NotImplementedError()

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


class PrivateGitLab(GitLab):
    """The private GitLab instance."""

    def load_defaults(self) -> None:
        """Load the values for this git service from the ini configuration and environment variables.

        In this case, the environment variable ``MCN_PRIVATE_GITLAB_TOKEN`` holding
        the access token for the private GitLab service is expected.

        Raises
        ------
        ConfigurationError
            If there is an error loading the configuration.
        """
        try:
            self.domain = self.load_domain(section_name="git_service.gitlab.private")
        except ConfigurationError as error:
            raise error

        if not self.domain:
            return

        access_token_env_var = "MCN_PRIVATE_GITLAB_TOKEN"  # nosec B105
        self.access_token = os.environ.get(access_token_env_var)

        if not self.access_token:
            raise ConfigurationError(
                f"Environment variable '{access_token_env_var}' is not set for private GitLab service '{self.domain}'."
            )


class PublicGitLab(GitLab):
    """The public GitLab instance."""

    def load_defaults(self) -> None:
        """Load the values for this git service from the ini configuration and environment variables.

        In this case, the environment variable ``MCN_PUBLIC_GITLAB_TOKEN`` holding
        the access token for the public GitLab service is optional.

        Raises
        ------
        ConfigurationError
            If there is an error loading the configuration.
        """
        try:
            self.domain = self.load_domain(section_name="git_service.gitlab.public")
        except ConfigurationError as error:
            raise error

        self.access_token = os.environ.get("MCN_PUBLIC_GITLAB_TOKEN")
