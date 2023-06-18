# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BaseBuildTool class to be inherited by other specific Build Tools."""

import glob
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from macaron.dependency_analyzer import DependencyAnalyzer, NoneDependencyAnalyzer

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
    files_detected = glob.iglob(pattern, recursive=True)
    try:
        next(files_detected)
        return True
    except StopIteration:
        return False


class BaseBuildTool(ABC):
    """This abstract class is used to implement Build Tools."""

    def __init__(self, name: str) -> None:
        """Initialize instance.

        Parameters
        ----------
        name : str
            The name of this build tool.
        """
        self.name = name
        self.entry_conf: list[str] = []
        self.build_configs: list[str] = []
        self.package_lock: list[str] = []
        self.builder: list[str] = []
        self.packager: list[str] = []
        self.publisher: list[str] = []
        self.interpreter: list[str] = []
        self.interpreter_flag: list[str] = []
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
        self.project_name: str = ""

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

    @abstractmethod
    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""

    @abstractmethod
    def get_dep_analyzer(self, repo_path: str) -> DependencyAnalyzer:
        """Create a DependencyAnalyzer for the build tool.

        Parameters
        ----------
        repo_path: str
            The path to the target repo.

        Returns
        -------
        DependencyAnalyzer
            The DependencyAnalyzer object.
        """

    def get_build_dirs(self, repo_path: str) -> Iterable[Path]:
        """Find directories in the repository that have their own build scripts.

        This is especially important for applications that consist of multiple services.

        Parameters
        ----------
        repo_path: str
            The path to the target repo.

        Yields
        ------
        Path
            The relative paths from the repo path that contain build scripts.
        """
        config_paths: set[str] = set()
        for build_cfg in self.build_configs:
            config_paths.update(
                path
                for path in glob.glob(os.path.join(repo_path, "**", build_cfg), recursive=True)
                if self.is_detected(str(Path(path).parent))
            )

        list_iter = iter(sorted(config_paths, key=lambda x: (str(Path(x).parent), len(Path(x).parts))))
        try:
            cfg_path = next(list_iter)
            yield Path(cfg_path).parent.relative_to(repo_path)
            while next_item := next(list_iter):
                if next_item.startswith(str(Path(cfg_path).parent)):
                    continue
                cfg_path = next_item
                yield Path(next_item).parent.relative_to(repo_path)

        except StopIteration:
            pass


class NoneBuildTool(BaseBuildTool):
    """This class can be used to initialize an empty build tool."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="")

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
        return False

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
        return False

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""

    def get_dep_analyzer(self, repo_path: str) -> DependencyAnalyzer:
        """Create an invalid DependencyAnalyzer for the empty build tool.

        Parameters
        ----------
        repo_path: str
            The path to the target repo.

        Returns
        -------
        DependencyAnalyzer
            The DependencyAnalyzer object.
        """
        return NoneDependencyAnalyzer()
