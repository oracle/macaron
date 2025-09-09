# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the base class and core data models for repository verification."""
import abc
import logging
from dataclasses import dataclass
from enum import Enum

from macaron.slsa_analyzer.build_tool import BaseBuildTool

logger = logging.getLogger(__name__)


class RepositoryVerificationStatus(str, Enum):
    """A class to store the status of the repo verification."""

    #: We found evidence to prove that the repository can be linked back to the publisher of the artifact.
    PASSED = "passed"

    #: We found evidence showing that the repository is not the publisher of the artifact.
    FAILED = "failed"

    #: We could not find any evidence to prove or disprove that the repository can be linked back to the artifact.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RepositoryVerificationResult:
    """A class to store the information about repository verification."""

    #: The status of the repository verification.
    status: RepositoryVerificationStatus

    #: The reason for the verification result.
    reason: str

    #: The build tool used to build the package.
    build_tool: BaseBuildTool


class RepoVerifierBase(abc.ABC):
    """The base class to verify whether a reported repository links back to the artifact."""

    @abc.abstractmethod
    def verify_repo(self) -> RepositoryVerificationResult:
        """Verify whether the repository links back to the artifact.

        Returns
        -------
        RepositoryVerificationResult
            The result of the repository verification
        """


class RepoVerifierFromProvenance(RepoVerifierBase):
    """An implementation of the base verifier that verifies a repository if the URL comes from provenance."""

    DEFAULT_REASON = "from_provenance"

    def __init__(
        self,
        namespace: str | None,
        name: str,
        version: str,
        reported_repo_url: str,
        reported_repo_fs: str,
        provenance_repo_url: str | None,
        build_tool: BaseBuildTool,
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
        provenance_repo_url : str | None
            The URL of the repository from a provenance file, or None if it, or the provenance, is not present.
        build_tool : BaseBuildTool
            The build tool used to build the package.
        """
        self.namespace = namespace
        self.name = name
        self.version = version
        self.reported_repo_url = reported_repo_url
        self.reported_repo_fs = reported_repo_fs
        self.provenance_repo_url = provenance_repo_url
        self.build_tool = build_tool

    def verify_repo(self) -> RepositoryVerificationResult:
        """Verify whether the repository links back to the artifact from the provenance URL."""
        if self.provenance_repo_url:
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.PASSED,
                reason=RepoVerifierFromProvenance.DEFAULT_REASON,
                build_tool=self.build_tool,
            )

        return RepositoryVerificationResult(
            status=RepositoryVerificationStatus.UNKNOWN, reason="unsupported_type", build_tool=self.build_tool
        )


class RepoVerifierToolSpecific(RepoVerifierFromProvenance, abc.ABC):
    """An abstract subclass of the repo verifier that provides and calls a per-tool verification function.

    From-provenance verification is inherited from the parent class.
    """

    def __init__(
        self,
        namespace: str | None,
        name: str,
        version: str,
        reported_repo_url: str,
        reported_repo_fs: str,
        build_tool: BaseBuildTool,
        provenance_repo_url: str | None,
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
        build_tool : BaseBuildTool
            The build tool used to build the package.
        provenance_repo_url : str | None
            The URL of the repository from a provenance file, or None if it, or the provenance, is not present.
        """
        super().__init__(namespace, name, version, reported_repo_url, reported_repo_fs, provenance_repo_url, build_tool)

    def verify_repo(self) -> RepositoryVerificationResult:
        """Verify the repository as per the base class method."""
        result = super().verify_repo()
        if result.status == RepositoryVerificationStatus.PASSED:
            return result

        return self.verify_by_tool()

    @abc.abstractmethod
    def verify_by_tool(self) -> RepositoryVerificationResult:
        """Verify the repository using build tool specific methods."""
