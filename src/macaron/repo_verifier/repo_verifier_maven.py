# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains code to verify whether a reported repository with Maven build system can be linked back to the artifact."""
import logging
from pathlib import Path
from urllib.parse import urlparse

from macaron.parsers.pomparser import parse_pom_string
from macaron.repo_verifier.repo_verifier_base import (
    RepositoryVerificationResult,
    RepositoryVerificationStatus,
    RepoVerifierBase,
    find_file_in_repo,
)
from macaron.slsa_analyzer.build_tool import Maven
from macaron.slsa_analyzer.package_registry.maven_central_registry import (
    RECOGNIZED_CODE_HOSTING_SERVICES,
    same_organization,
)

logger = logging.getLogger(__name__)


class RepoVerifierMaven(RepoVerifierBase):
    """A class to verify whether a repository with Maven build tool links back to the artifact."""

    build_tool = Maven()

    def verify_repo(self) -> RepositoryVerificationResult:
        """Verify whether the reported repository links back to the Maven artifact.

        Returns
        -------
        RepositoryVerificationResult
            The result of the repository verification
        """
        if not self.namespace:
            logger.debug("No namespace provided for Maven verification.")
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN, reason="no_namespace", build_tool=self.build_tool
            )

        recognized_services_verification_result = self.verify_domains_from_recognized_code_hosting_services()
        if recognized_services_verification_result.status == RepositoryVerificationStatus.PASSED:
            return recognized_services_verification_result

        # TODO: check other pom files. Think about how to decide in case of contradicting evidence.
        # Check if repo contains pom.xml.
        pom_file = find_file_in_repo(Path(self.reported_repo_fs), "pom.xml")
        if not pom_file:
            logger.debug("Could not find any pom.xml in the repository: %s", self.reported_repo_url)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN, reason="no_pom", build_tool=self.build_tool
            )

        pom_content = pom_file.read_text(encoding="utf-8")
        pom_root = parse_pom_string(pom_content)

        if not pom_root:
            logger.debug("Could not parse pom.xml: %s", pom_file.as_posix())
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN, reason="not_parsed_pom", build_tool=self.build_tool
            )

        # Find the group id in the pom (project/groupId).
        # The closing curly brace represents the end of the XML namespace.
        pom_group_id_elem = next((ch for ch in pom_root if ch.tag.endswith("}groupId")), None)
        if pom_group_id_elem is None or not pom_group_id_elem.text:
            logger.debug("Could not find groupId in pom.xml: %s", pom_file)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN, reason="no_group_id_in_pom", build_tool=self.build_tool
            )

        pom_group_id = pom_group_id_elem.text.strip()
        if not same_organization(pom_group_id, self.namespace):
            logger.debug("Group id in pom.xml does not match the provided group id: %s", pom_file)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.FAILED, reason="group_id_mismatch", build_tool=self.build_tool
            )

        return RepositoryVerificationResult(
            status=RepositoryVerificationStatus.PASSED, reason="group_id_match", build_tool=self.build_tool
        )

    def verify_domains_from_recognized_code_hosting_services(self) -> RepositoryVerificationResult:
        """Verify repository link by comparing the maven domain name and the account on code hosting services.

        This verification relies on the fact that Sonatype recognizes
        certain code hosting platforms for namespace verification on maven central.

        Returns
        -------
        RepositoryVerificationResult
            The result of the repository verification
        """
        if not self.namespace:
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN, reason="no_namespace", build_tool=self.build_tool
            )

        parsed_url = urlparse(self.reported_repo_url)
        if parsed_url is None or not parsed_url.hostname:
            logger.debug("Could not parse the claimed repository URL: %s", self.reported_repo_url)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN, reason="url_parse_error", build_tool=self.build_tool
            )

        reported_hostname = parsed_url.hostname.split(".")[0]
        reported_account = parsed_url.path.strip("/").split("/")[0]

        group_parts = self.namespace.split(".")
        for platform in RECOGNIZED_CODE_HOSTING_SERVICES:
            # For artifacts from recognized code hosting services, check if the
            # organization name is the same in maven and the source repository.
            # For example, com.github.foo matches github.com/foo,
            # but it doesn't match gitlab.com/foo or gitlab.com/bar.
            if (
                group_parts[0].lower() in {"io", "com"}
                and group_parts[1].lower() == platform.lower()  # E.g., github.
                and group_parts[1].lower() == reported_hostname.lower()  # E.g., github.
                and group_parts[2].lower() == reported_account.lower()  # E.g., foo in github.com/foo.
            ):
                return RepositoryVerificationResult(
                    status=RepositoryVerificationStatus.PASSED, reason="git_ns_match", build_tool=self.build_tool
                )

        return RepositoryVerificationResult(
            # Not necessarily a fail, because many projects use maven group ids other than their repo domain.
            status=RepositoryVerificationStatus.UNKNOWN,
            reason="git_ns_mismatch",
            build_tool=self.build_tool,
        )
