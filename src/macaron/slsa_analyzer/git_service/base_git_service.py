# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BaseGitService class to be inherited by a git service."""

from abc import abstractmethod

from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError


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

        The section may or may not be available in the configuration. In both case,
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
            The domain. This can be ``None`` if the git section is not found in
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
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError


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
