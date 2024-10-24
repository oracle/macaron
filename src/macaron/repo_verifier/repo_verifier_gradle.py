# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains code to verify whether a repository with Gradle build system can be linked back to the artifact."""
import logging
from pathlib import Path

from macaron.artifact.maven import is_valid_maven_group_id
from macaron.repo_verifier.repo_verifier_base import (
    RepositoryVerificationResult,
    RepositoryVerificationStatus,
    RepoVerifierBase,
    find_file_in_repo,
)
from macaron.repo_verifier.repo_verifier_maven import RepoVerifierMaven
from macaron.slsa_analyzer.build_tool import Gradle
from macaron.slsa_analyzer.package_registry.maven_central_registry import same_organization

logger = logging.getLogger(__name__)


class RepoVerifierGradle(RepoVerifierBase):
    """A class to verify whether a repository with Gradle build tool links back to the artifact."""

    build_tool = Gradle()

    def __init__(
        self,
        namespace: str,
        name: str,
        version: str,
        reported_repo_url: str,
        reported_repo_fs: str,
    ):
        """Initialize a RepoVerifierGradle instance.

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
        super().__init__(namespace, name, version, reported_repo_url, reported_repo_fs)

        self.maven_verifier = RepoVerifierMaven(
            namespace=namespace,
            name=name,
            version=version,
            reported_repo_url=reported_repo_url,
            reported_repo_fs=reported_repo_fs,
        )

    def verify_repo(self) -> RepositoryVerificationResult:
        """Verify whether the reported repository links back to the artifact.

        Returns
        -------
        RepositoryVerificationResult
            The result of the repository verification
        """
        if not self.namespace:
            logger.debug("No namespace provided for Gradle verification.")
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN, reason="no_namespace", build_tool=self.build_tool
            )

        recognized_services_verification_result = (
            self.maven_verifier.verify_domains_from_recognized_code_hosting_services()
        )
        if recognized_services_verification_result.status == RepositoryVerificationStatus.PASSED:
            return recognized_services_verification_result

        gradle_group_id = self._extract_group_id_from_properties()
        if not gradle_group_id:
            gradle_group_id = self._extract_group_id_from_build_groovy()
        if not gradle_group_id:
            gradle_group_id = self._extract_group_id_from_build_kotlin()
        if not gradle_group_id:
            logger.debug("Could not find group from gradle manifests for %s", self.reported_repo_url)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN,
                reason="no_group_in_gradle_manifest",
                build_tool=self.build_tool,
            )

        if not same_organization(gradle_group_id, self.namespace):
            logger.debug("Group in gradle manifest does not match the provided group id: %s", self.reported_repo_url)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.FAILED, reason="group_id_mismatch", build_tool=self.build_tool
            )

        return RepositoryVerificationResult(
            status=RepositoryVerificationStatus.PASSED, reason="group_id_match", build_tool=self.build_tool
        )

    def _extract_group_id_from_gradle_manifest(
        self, file_path: Path | None, quote_chars: set[str] | None = None, delimiter: str = "="
    ) -> str | None:
        """Extract the group id from a gradle build or config file.

        Parameters
        ----------
        file_path : Path | None
            The path to the file.
        quote_chars : set[str] | None
            The characters used to quote the group id.
        delimiter : str
            The delimiter used in the file.

        Returns
        -------
        str | None
            The extracted group id. None if not found.
        """
        if not file_path:
            logger.debug("Could not find the file %s in the repository: %s", file_path, self.reported_repo_url)
            return None

        file_content = file_path.read_text().splitlines()
        for line in file_content:
            line_parts = list(filter(None, map(str.strip, line.strip().lower().split(delimiter))))
            if len(line_parts) != 2:
                continue

            if line_parts[0] != "group":
                continue

            group_id = line_parts[1]

            # Check if the value for group_id is a string literal.
            if quote_chars:
                if group_id[0] not in quote_chars or group_id[-1] not in quote_chars or group_id[0] != group_id[-1]:
                    continue
                group_id = group_id[1:-1]

            if is_valid_maven_group_id(group_id):
                return group_id

        return None

    def _extract_group_id_from_properties(self) -> str | None:
        """Extract the group id from the gradle.properties file."""
        gradle_properties = find_file_in_repo(Path(self.reported_repo_fs), "gradle.properties")
        return self._extract_group_id_from_gradle_manifest(gradle_properties)

    def _extract_group_id_from_build_groovy(self) -> str | None:
        """Extract the group id from the build.gradle file."""
        build_gradle = find_file_in_repo(Path(self.reported_repo_fs), "build.gradle")
        return self._extract_group_id_from_gradle_manifest(build_gradle, quote_chars={"'", '"'}, delimiter=" ")

    def _extract_group_id_from_build_kotlin(self) -> str | None:
        """Extract the group id from the build.gradle.kts file."""
        build_gradle = find_file_in_repo(Path(self.reported_repo_fs), "build.gradle.kts")
        return self._extract_group_id_from_gradle_manifest(build_gradle, quote_chars={'"'}, delimiter="=")
