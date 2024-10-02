# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the base class and core data models for repository verification."""
import abc
import logging
import os
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from macaron.slsa_analyzer.build_tool import BaseBuildTool

logger = logging.getLogger(__name__)


def find_file_in_repo(root_dir: Path, filename: str) -> Path | None:
    """Find the highest level file with a given name in a local repository.

    This function ignores certain paths that are not under the main source code directories.
    """
    if not os.path.exists(root_dir) or not os.path.isdir(root_dir):
        return None

    queue: deque[Path] = deque()
    queue.append(Path(root_dir))
    while queue:
        current_dir = queue.popleft()

        # Don't look through non-main directories.
        if any(
            keyword in current_dir.name.lower()
            for keyword in ["test", "example", "sample", "doc", "demo", "spec", "mock"]
        ):
            continue

        if Path(current_dir, filename).exists():
            return Path(current_dir, filename)

        # Ignore symlinks to prevent potential infinite loop.
        sub_dirs = [Path(it) for it in current_dir.iterdir() if it.is_dir() and not it.is_symlink()]
        queue.extend(sub_dirs)

    return None


class RepositoryVerificationStatus(str, Enum):
    """A class to store the status of the repo verification."""

    # We found evidence to prove that the repository can be linked back to the publisher of the artifact.
    PASSED = "passed"

    # We found evidence showing that the repository is not the publisher of the artifact.
    FAILED = "failed"

    # We could not find any evidence to prove or disprove that the repository can be linked back to the artifact.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RepositoryVerificationResult:
    """A class to store the information about repository verification."""

    status: RepositoryVerificationStatus
    reason: str
    build_tool: BaseBuildTool


class RepoVerifierBase(abc.ABC):
    """The base class to verify whether a reported repository links back to the artifact."""

    @property
    @abc.abstractmethod
    def build_tool(self) -> BaseBuildTool:
        """Define the build tool used to build the package."""

    def __init__(
        self,
        namespace: str | None,
        name: str,
        version: str,
        reported_repo_url: str,
        reported_repo_fs: str,
    ):
        """Instantiate the class.

        Parameters
        ----------
        namespace : str
            The namespace of the artifact.
        name : str
            The name of the artifact.
        version : str
            The version of the artifact.
        reported_repo_url : str
            The URL of the repository reported by the publisher.
        reported_repo_fs : str
            The file system path of the reported repository.
        """
        self.namespace = namespace
        self.name = name
        self.version = version
        self.reported_repo_url = reported_repo_url
        self.reported_repo_fs = reported_repo_fs

    @abc.abstractmethod
    def verify_repo(self) -> RepositoryVerificationResult:
        """Verify whether the repository links back to the artifact."""
