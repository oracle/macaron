# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BaseGitService class to be inherited by a git service."""

from abc import abstractmethod

from pydriller.git import Git

from macaron.config.defaults import defaults
from macaron.errors import CloneError, ConfigurationError, RepoCheckOutError
from macaron.slsa_analyzer import git_url


class BaseGitService:
    """This abstract class is used to implement git services."""

    def __init__(self, name: str) -> None:
        """Initialize instance.

        Parameters
        ----------
        name : str
            The name of the git service.
        """
        self.name = name
        self.domain: str | None = None

    @abstractmethod
    def load_defaults(self) -> None:
        """Load the values for this git service from the ini configuration."""
        raise NotImplementedError

    def load_domain(self, section_name: str) -> str | None:
        """Load the domain of the git service from the ini configuration section ``section_name``.

        The section may or may not be available in the configuration. In both cases,
        the method should not raise ``ConfigurationError``.

        Meanwhile, if the section is present but there is a schema violation (e.g. a key such as
        ``domain`` is missing), this method will raise a ``ConfigurationError``.

        Parameters
        ----------
        section_name : str
            The name of the git service section in the ini configuration file.

        Returns
        -------
        str | None
            The domain. This can be ``None`` if the git service section is not found in
            the ini configuration file, meaning the user does not enable the
            corresponding git service.

        Raises
        ------
        ConfigurationError
            If there is a schema violation in the git service section.
        """
        if not defaults.has_section(section_name):
            # We do not raise ConfigurationError here because it is not compulsory
            # to have all available git services in the ini config.
            return None
        section = defaults[section_name]
        domain = section.get("domain")
        if not domain:
            raise ConfigurationError(
                f'The "domain" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        return domain

    def is_detected(self, url: str) -> bool:
        """Check if the remote repo at the given ``url`` is hosted on this git service.

        This check is done by checking the URL of the repo against the domain of this
        git service.

        Parameters
        ----------
        url : str
            The url of the remote repo.

        Returns
        -------
        bool
            True if the repo is indeed hosted on this git service.
        """
        if self.domain is None:
            return False
        return (
            git_url.parse_remote_url(
                url,
                allowed_git_service_domains=[self.domain],
            )
            is not None
        )

    @abstractmethod
    def clone_repo(self, clone_dir: str, url: str) -> None:
        """Clone a repository.

        Parameters
        ----------
        clone_dir: str
            The name of the directory to clone into.
            This is equivalent to the <directory> argument of ``git clone``.
        url : str
            The url to the repository.

        Raises
        ------
        CloneError
            If there is an error cloning the repo.
        """
        raise NotImplementedError()

    @abstractmethod
    def check_out_repo(self, git_obj: Git, branch: str, digest: str, offline_mode: bool) -> Git:
        """Checkout the branch and commit specified by the user of a repository.

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
            If there is an error while checking out the specific branch or commit.
        """
        raise NotImplementedError()


class NoneGitService(BaseGitService):
    """This class can be used to initialize an empty git service."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__("")

    def load_defaults(self) -> None:
        """Load the values for this git service from the ini configuration.

        In this particular case, since this class represents a ``None`` git service,
        we do nothing.
        """

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
        return False

    def clone_repo(self, _clone_dir: str, url: str) -> None:
        """Clone a repo.

        In this particular case, since this class represents a ``None`` git service,
        we do nothing but raise a ``CloneError``.

        Raises
        ------
        CloneError
            Always raise, since this method should not be used to clone any repository.
        """
        raise CloneError(f"Internal error encountered when cloning the repo '{url}'.")

    def check_out_repo(self, git_obj: Git, branch: str, digest: str, offline_mode: bool) -> Git:
        """Checkout the branch and commit specified by the user of a repository.

        In this particular case, since this class represents a ``None`` git service,
        we do nothing but raise a ``RepoError``.

        Raises
        ------
        RepoError
            Always raise, since this method should not be used to check out in any repository.
        """
        raise RepoCheckOutError(
            f"Internal error when checking out branch {branch} and commit {digest} for repo {git_obj.project_name}."
        )
