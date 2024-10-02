# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains code to verify whether a reported repository can be linked back to the artifact."""
import logging

from macaron.repo_verifier.repo_verifier_base import (
    RepositoryVerificationResult,
    RepositoryVerificationStatus,
    RepoVerifierBase,
)
from macaron.repo_verifier.repo_verifier_gradle import RepoVerifierGradle
from macaron.repo_verifier.repo_verifier_maven import RepoVerifierMaven
from macaron.slsa_analyzer.build_tool import BaseBuildTool, Gradle, Maven

logger = logging.getLogger(__name__)


def verify_repo(
    namespace: str | None,
    name: str,
    version: str,
    reported_repo_url: str,
    reported_repo_fs: str,
    build_tool: BaseBuildTool,
) -> RepositoryVerificationResult:
    """Verify whether the repository links back to the artifact.

    Parameters
    ----------
    namespace : str | None
        The namespace of the artifact.
    name : str
        The name of the artifact.
    version : str
        The version of the artifact.
    reported_repo_url : str
        The reported repository URL.
    reported_repo_fs : str
        The reported repository filesystem path.
    build_tool : BaseBuildTool
        The build tool used to build the package.

    Returns
    -------
    RepositoryVerificationResult
        The result of the repository verification
    """
    # TODO: Add support for other build tools.
    verifier_map: dict[type[BaseBuildTool], type[RepoVerifierBase]] = {
        Maven: RepoVerifierMaven,
        Gradle: RepoVerifierGradle,
        # Poetry(): RepoVerifierPoetry,
        # Pip(): RepoVerifierPip,
        # Docker(): RepoVerifierDocker,
        # NPM(): RepoVerifierNPM,
        # Yarn(): RepoVerifierYarn,
        # Go(): RepoVerifierGo,
    }

    verifier_cls = verifier_map.get(type(build_tool))
    if not verifier_cls:
        return RepositoryVerificationResult(
            status=RepositoryVerificationStatus.UNKNOWN, reason="unsupported_type", build_tool=build_tool
        )

    verifier = verifier_cls(
        namespace=namespace,
        name=name,
        version=version,
        reported_repo_url=reported_repo_url,
        reported_repo_fs=reported_repo_fs,
    )

    return verifier.verify_repo()
