# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for the GitLab service.

Note: We are making the assumption that we are only supporting two different GitLab
services: one is called ``publicly_hosted`` and the other is called ``self_hosted``.

The corresponding access tokens are stored in the environment variables
``MCNGITLAB_TOKEN`` and ``MCN_SELF_HOSTED_GITLAB_TOKEN``, respectively.

Reason for this is mostly because of our assumption that Macaron is used as a
container. Fixing static names for the environment variables allows for easier
propagation of these variables into the container.

In the ini configuration file, settings for the ``publicly_hosted`` GitLab service is in the
``[git_service.gitlab.publicly_hosted]`` section; settings for the ``self_hosted`` GitLab service
is in the ``[git_service.gitlab.self_hosted]`` section.
"""

import logging
import os
from abc import abstractmethod
from urllib.parse import ParseResult, urlunparse

from macaron.errors import CloneError, ConfigurationError
from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService

logger: logging.Logger = logging.getLogger(__name__)


class GitLab(BaseGitService):
    """This class contains the spec of the GitLab service."""

    def __init__(self, access_token_env_name: str) -> None:
        """Initialize instance."""
        super().__init__("gitlab")
        self.access_token_env_name = access_token_env_name

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

        # Construct clone URL from ``urlparse`` result, with or without an access token.
        # https://docs.gitlab.com/ee/gitlab-basics/start-using-git.html#clone-using-a-token
        access_token = os.environ.get(self.access_token_env_name)
        if access_token:
            clone_url_netloc = f"oauth2:{access_token}@{self.domain}"
        else:
            clone_url_netloc = self.domain

        clone_url = urlunparse(
            ParseResult(
                scheme=url_parse_result.scheme,
                netloc=clone_url_netloc,
                path=url_parse_result.path,
                params="",
                query="",
                fragment="",
            )
        )

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


class SelfHostedGitLab(GitLab):
    """The self-hosted GitLab instance."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__("MCN_SELF_HOSTED_GITLAB_TOKEN")

    def load_defaults(self) -> None:
        """Load the values for this git service from the ini configuration and environment variables.

        In this case, the environment variable ``MCN_SELF_HOSTED_GITLAB_TOKEN`` holding
        the access token for the private GitLab service is expected.

        Raises
        ------
        ConfigurationError
            If there is an error loading the configuration.
        """
        try:
            self.domain = self.load_domain(section_name="git_service.gitlab.self_hosted")
        except ConfigurationError as error:
            raise error

        if not self.domain:
            return

        if not os.environ.get(self.access_token_env_name):
            raise ConfigurationError(
                f"Environment variable '{self.access_token_env_name}' is not set "
                + f"for private GitLab service '{self.domain}'."
            )


class PubliclyHostedGitLab(GitLab):
    """The publicly-hosted GitLab instance."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__("MCN_GITLAB_TOKEN")

    def load_defaults(self) -> None:
        """Load the values for this git service from the ini configuration and environment variables.

        In this case, the environment variable ``MCN_GITLAB_TOKEN`` holding
        the access token for the public GitLab service is optional.

        Raises
        ------
        ConfigurationError
            If there is an error loading the configuration.
        """
        try:
            self.domain = self.load_domain(section_name="git_service.gitlab.publicly_hosted")
        except ConfigurationError as error:
            raise error
