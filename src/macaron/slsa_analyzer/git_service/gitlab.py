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

import logging
import os
from abc import abstractmethod

from macaron.errors import CloneError, ConfigurationError
from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService

logger: logging.Logger = logging.getLogger(__name__)


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

    def construct_clone_url(self, url: str) -> str:
        """Construct a clone URL for GitLab, with or without access token.

        Parameters
        ----------
        url : str
            The URL of the repository to be cloned.

        Returns
        -------
        str
            The URL that is actually used for cloning, containing the access token.
            See GitLab documentation: https://docs.gitlab.com/ee/gitlab-basics/start-using-git.html#clone-using-a-token.

        Raises
        ------
        CloneError
            If there is an error parsing the URL.
        """
        if not self.domain:
            # This should not happen.
            logger.debug("Cannot clone with a Git service having no domain.")
            raise CloneError(f"Cannot clone the repo '{url}' due to an internal error.")

        url_parse_result = git_url.parse_remote_url(
            url,
            allowed_git_service_domains=[self.domain],
        )
        if not url_parse_result:
            raise CloneError(
                f"Cannot clone the repo '{url}' due to the URL format being invalid or not supported by Macaron."
            )

        if self.access_token:
            # https://docs.gitlab.com/ee/gitlab-basics/start-using-git.html#clone-using-a-token
            clone_url = f"https://oauth2:{self.access_token}@{self.domain}/{url_parse_result.path}"
        else:
            clone_url = f"https://{self.domain}/{url_parse_result.path}"

        return clone_url

    def clone_repo(self, clone_dir: str, url: str) -> None:
        """Clone a repository.

        To clone a GitLab repository with access token, we embed the access token in the https URL.
        See GitLab documentation: https://docs.gitlab.com/ee/gitlab-basics/start-using-git.html#clone-using-a-token.

        Parameters
        ----------
        clone_dir: str
            The name of the directory to clone into.
            This is equivalent to the <directory> argument of ``git clone``.
        url : str
            The url to the GitLab repository.

        Raises
        ------
        CloneError
            If there is an error cloning the repository.
        """
        clone_url = self.construct_clone_url(url)
        git_url.clone_remote_repo(clone_dir, clone_url)


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
