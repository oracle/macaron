# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BaseBuildTool class to be inherited by other specific Build Tools."""

import glob
import logging
import os
from abc import abstractmethod

logger: logging.Logger = logging.getLogger(__name__)


def file_exists(path: str, file_name: str) -> bool:
    """Return True if a file exists in a directory.

    This method searches in the directory recursively.

    Parameters
    ----------
    path : str
        The path to search for the file.
    file_name : str
        The name of the file to search.

    Returns
    -------
    bool
        True if file_name exists else False.
    """
    pattern = os.path.join(path, "**", file_name)
    files_detected = glob.glob(pattern, recursive=True)
    if files_detected:
        return True

    return False


def _find_parent_file_in(path: str, name: str) -> str:
    """Return the path to the highest level file in a directory given its name.

    When only one instance of that file exists, this method will return the path
    to that file.

    When multiple instances of that file exists, this method will ONLY return the path
    to the highest level instance of that file.

    Parameters
    ----------
    path : str
        The path to the target dir.
    name : str
        The name of the file to search for.

    Returns
    -------
    str
        The path to the highest level file or empty if errors.

    Examples
    --------
    .. code-block: bash
        :caption: Given a dir as below

        a/
        ├── pom.xml
        ├── b
        │   └── pom.xml
        └── c
            └── d
                └── pom.xml
            └── e
                └── pom.xml

    >>> _find_parent_file_in("a", "pom.xml")
    'a/pom.xml'

    >>> _find_parent_file_in("a/b", "pom.xml")
    'a/b/pom.xml'

    >>> _find_parent_file_in("a/b/c", "pom.xml")
    ''
    """
    # Search for all files in the path.
    files_detected = glob.glob(os.path.join(path, "**", name), recursive=True)
    if not files_detected:
        logger.debug("Cannot find any %s in %s", name, path)
        return ""

    # Return if there is only one instance of the file
    # This is to avoid using os.path.commonpath on a single path,
    # which would return that path instead of a parent dir.
    if len(files_detected) == 1:
        return files_detected.pop()

    # Get the path of the highest level file.
    common_path = os.path.commonpath(files_detected)
    parent_file = glob.glob(os.path.join(common_path, name))

    # There cannot be two same instances of a file in the same dir.
    if len(parent_file) > 1:
        logger.critical("Find two instances of %s in %s", name, common_path)
        return ""

    if not parent_file:
        logger.debug("Cannot find the parent %s in the path %s", name, path)
        return ""

    parent_file_path = parent_file.pop()
    logger.debug("Found parent %s at %s", name, parent_file_path)
    return parent_file_path


class BaseBuildTool:
    """This abstract class is used to implement Build Tools.

    Parameters
    ----------
    name : str
        The name of this build tool.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.entry_conf: list[str] = []
        self.build_configs: list[str] = []
        self.builder: list[str] = []
        self.build_arg: list[str] = []
        self.deploy_arg: list[str] = []
        self.ci_build_kws: dict[str, list[str]] = {
            "github_actions": [],
            "travis_ci": [],
            "circle_ci": [],
            "gitlab_ci": [],
            "jenkins": [],
        }
        self.ci_deploy_kws: dict[str, list[str]] = {
            "github_actions": [],
            "travis_ci": [],
            "circle_ci": [],
            "gitlab_ci": [],
            "jenkins": [],
        }
        self.build_log: list[str] = []
        self.wrapper_files: list[str] = []

    def __str__(self) -> str:
        return self.name

    @abstractmethod
    def is_detected(self, repo_path: str) -> bool:
        """Return True if this build tool is used in the target repo.

        Parameters
        ----------
        repo_path : str
            The path to the target repo.

        Returns
        -------
        bool
            True if this build tool is detected, else False.
        """
        raise NotImplementedError

    @abstractmethod
    def prepare_config_files(self, wrapper_path: str, build_dir: str) -> bool:
        """Prepare the necessary wrapper files for running the build.

        This method will return False if there is any errors happened during operation.

        Parameters
        ----------
        wrapper_path : str
            The path where all necessary wrapper files are located.
        build_dir : str
            The path of the build dir. This is where all files are copied to.

        Returns
        -------
        bool
            True if succeed else False.
        """
        raise NotImplementedError

    @abstractmethod
    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        raise NotImplementedError


class NoneBuildTool(BaseBuildTool):
    """This class can be used to initialize an empty build tool."""

    def __init__(self) -> None:
        super().__init__(name="")

    def is_detected(self, repo_path: str) -> bool:
        return False

    def prepare_config_files(self, wrapper_path: str, build_dir: str) -> bool:
        return False

    def load_defaults(self) -> None:
        pass
