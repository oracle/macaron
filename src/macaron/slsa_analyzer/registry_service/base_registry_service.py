"""This module contains the BaseRegistryService class to be inherited by a registry service."""

from abc import abstractmethod


class BaseRegistryService:
    """This abstract class is used to implement registry services."""

    def __init__(self, name: str) -> None:
        """Initialize instance.

        Parameters
        ----------
        name : str
            The name of the registry service.
        """
        self.name = name

    @abstractmethod
    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        raise NotImplementedError

    @abstractmethod
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


class NoneRegistryService(BaseRegistryService):
    """This class can be used to initialize an empty registry service."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__("")

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""

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
