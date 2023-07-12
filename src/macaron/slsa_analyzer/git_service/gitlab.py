# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for the GitLab service.

Note: We are making the assumption that we are only supporting two different GitLab
services: one is called ``publicly_hosted`` and the other is called ``self_hosted``.

The corresponding access tokens are stored in the environment variables
``MCN_GITLAB_TOKEN`` and ``MCN_SELF_HOSTED_GITLAB_TOKEN``, respectively.

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

from pydriller.git import Git

from macaron.errors import CloneError, ConfigurationError, RepoCheckOutError
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

        If we clone using the https URL with the token embedded, this URL will be store as plain text in .git/config as
        the origin remote URL. Therefore, after a repository is cloned, this remote origin URL will be set
        with the value of the original ``url`` (which does not have the embed token).

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
        repo = git_url.clone_remote_repo(clone_dir, clone_url)

        # If ``git_url.clone_remote_repo`` return an Repo instance, this means that the repository is freshly cloned
        # with the token embedded URL. We will set its value back to the original non-token URL.
        # If ``git_url.clone_remote_repo`` returns None, it means that the repository already exists so we don't need
        # to do anything.
        if repo:
            try:
                origin_remote = repo.remote("origin")
            except ValueError as error:
                raise CloneError("Cannot find the remote origin for this repository.") from error

            origin_remote.set_url(url)

    def check_out_repo(self, git_obj: Git, branch: str, digest: str, offline_mode: bool) -> Git:
        """Checkout the branch and commit specified by the user of a repository.

        For GitLab, this method set the origin remote URL of the target repository to the token-embedded URL if
        a token is available before performing the checkout operation.

        After the checkout operation finishes, the origin remote URL is set back again to ensure that no token-embedded
        URL remains.

        Parameters
        ----------
        git_obj : Git
            The Git object for the repository to check out.
        branch : str
            The branch to check out.
        digest : str
            The sha of the commit to check out.
        offline_mode: bool
            If true, no fetching is performed.

        Returns
        -------
        Git
            The same Git object from the input.

        Raises
        ------
        RepoError
            If there is error while checkout the specific branch and digest.
        """
        remote_origin_url = git_url.get_remote_origin_of_local_repo(git_obj)

        try:
            origin_remote = git_obj.repo.remote("origin")
        except ValueError as error:
            raise RepoCheckOutError("Cannot find the remote origin for this repository.") from error

        try:
            reconstructed_url = self.construct_clone_url(remote_origin_url)
        except CloneError as error:
            raise RepoCheckOutError("Internal error prevent preparing the repo for the analysis.") from error

        origin_remote.set_url(reconstructed_url, remote_origin_url)

        check_out_status = git_url.check_out_repo_target(git_obj, branch, digest, offline_mode)

        origin_remote.set_url(remote_origin_url, reconstructed_url)

        if not check_out_status:
            raise RepoCheckOutError(
                f"Internal error when checking out branch {branch} and commit {digest} for repo {git_obj.project_name}."
            )

        return git_obj


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
