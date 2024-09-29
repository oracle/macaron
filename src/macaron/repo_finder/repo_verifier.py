# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module exists to verify whether a claimed repo links back to the artifact."""
import logging
import os
import re
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from macaron.parsers.pomparser import parse_pom_string
from macaron.slsa_analyzer.build_tool import NPM, BaseBuildTool, Docker, Go, Gradle, Maven, Pip, Poetry, Yarn

logger = logging.getLogger(__name__)


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


class RepoVerifier:
    """A class to verify a claimed repo."""

    _known_maven_namespaces = {
        "github",
        "gitlab",
        "bitbucket",
        "gitee",
    }

    def __init__(
        self,
        namespace: str,
        name: str,
        version: str,
        claimed_repo_url: str,
        claimed_repo_fs: str,
        build_tool: BaseBuildTool,
    ):
        self.namespace = namespace
        self.name = name
        self.version = version
        self.claimed_repo_url = claimed_repo_url
        self.claimed_repo_fs = claimed_repo_fs
        self.build_tool = build_tool

    def verify_claimed_repo(self) -> RepositoryVerificationResult:
        """Verify whether the claimed repository links back to the artifact."""
        default_res = RepositoryVerificationResult(
            status=RepositoryVerificationStatus.UNKNOWN, reason="unsupported_type", build_tool=self.build_tool
        )

        match self.build_tool:
            case Maven():
                git_ns_ver = self._verify_maven_git_ns()
                if git_ns_ver.status == RepositoryVerificationStatus.PASSED:
                    return git_ns_ver
                return self._verify_maven()
            case Gradle():
                git_ns_ver = self._verify_maven_git_ns()
                if git_ns_ver.status == RepositoryVerificationStatus.PASSED:
                    return git_ns_ver
                return self._verify_gradle()
            # TODO: add verifiers for other types
            case Poetry():
                return default_res
            case Pip():
                return default_res
            case Docker():
                return default_res
            case NPM():
                return default_res
            case Yarn():
                return default_res
            case Go():
                return default_res
            case _:
                raise NotImplementedError(f"Unsupported build tool: {self.build_tool}")

    def _same_group(self, g1: str, g2: str) -> bool:
        if g1 == g2:
            return True

        g1_parts = g1.split(".")
        g2_parts = g2.split(".")
        if min(len(g1_parts), len(g2_parts)) < 2:
            return False

        if (g1_parts[0] in {"io", "com"} and g1_parts[1] in self._known_maven_namespaces) or (
            g2_parts[0] in {"io", "com"} and g2_parts[1] in self._known_maven_namespaces
        ):
            if len(g1_parts) >= 3 and len(g2_parts) >= 3:
                return all(g1_parts[i] == g2_parts[i] for i in range(3))
            return False

        for i in range(2):
            if g1_parts[i] != g2_parts[i]:
                return False

        return True

    @staticmethod
    def _bfs_walk(root_dir: Path, filename: str) -> Path | None:
        if not os.path.exists(root_dir) or not os.path.isdir(root_dir):
            return None

        queue: deque[Path] = deque()
        queue.append(Path(root_dir))
        while queue:
            current_dir = queue.popleft()

            # don't look through non-main directories
            if any(
                keyword in current_dir.name.lower()
                for keyword in ["test", "example", "sample", "doc", "demo", "spec", "mock"]
            ):
                continue

            if (current_dir / filename).exists():
                return current_dir / filename

            # ignore symlinks to prevent potential infinite loop
            sub_dirs = [Path(it) for it in current_dir.iterdir() if it.is_dir() and not it.is_symlink()]
            queue.extend(sub_dirs)

        return None

    def _verify_maven_git_ns(self) -> RepositoryVerificationResult:
        parsed_url = urlparse(self.claimed_repo_url)
        if parsed_url is None or parsed_url.hostname is None:
            logger.debug("Could not parse the claimed repository URL: %s", self.claimed_repo_url)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN, reason="url_parse_error", build_tool=self.build_tool
            )

        claimed_hostname = parsed_url.hostname.split(".")[0]
        claimed_account = parsed_url.path.strip("/").split("/")[0]

        group_parts = self.namespace.split(".")
        for platform in self._known_maven_namespaces:
            if (
                group_parts[0].lower() in {"io", "com"}
                and group_parts[1].lower() == platform.lower()
                and group_parts[1].lower() == claimed_hostname.lower()
                and group_parts[2].lower() == claimed_account.lower()
            ):
                return RepositoryVerificationResult(
                    status=RepositoryVerificationStatus.PASSED, reason="git_ns", build_tool=self.build_tool
                )

        return RepositoryVerificationResult(
            # not necessarily a fail, because many projects use maven group ids other than their repo domain.
            status=RepositoryVerificationStatus.UNKNOWN,
            reason="git_ns_mismatch",
            build_tool=self.build_tool,
        )

    def _verify_maven(self) -> RepositoryVerificationResult:
        # TODO: check other pom files. think about how to decide in case of contradicting evidence
        # check if repo contains pom.xml
        pom_file = self._bfs_walk(Path(self.claimed_repo_fs), "pom.xml")
        if pom_file is None:
            logger.debug("Could not find any pom.xml in the repository: %s", self.claimed_repo_url)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN, reason="no_pom", build_tool=self.build_tool
            )

        pom_content = pom_file.read_text()
        pom_root = parse_pom_string(pom_content)

        if not pom_root:
            logger.debug("Could not parse pom.xml: %s", pom_file.as_posix())
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN, reason="not_parsed_pom", build_tool=self.build_tool
            )

        # find the group id in the pom (project/groupId)
        pom_group_id_elem = next((ch for ch in pom_root if ch.tag.endswith("}groupId")), None)
        if pom_group_id_elem is None or pom_group_id_elem.text is None:
            logger.debug("Could not find groupId in pom.xml: %s", pom_file)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN, reason="no_group_id_in_pom", build_tool=self.build_tool
            )

        pom_group_id = pom_group_id_elem.text.strip()
        if not self._same_group(pom_group_id, self.namespace):
            logger.debug("Group id in pom.xml does not match the provided group id: %s", pom_file)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.FAILED, reason="group_id_mismatch", build_tool=self.build_tool
            )

        return RepositoryVerificationResult(
            status=RepositoryVerificationStatus.PASSED, reason="group_id_match", build_tool=self.build_tool
        )

    @staticmethod
    def _is_valid_maven_group_id(group_id: str) -> bool:
        pattern = r"^[a-zA-Z][a-zA-Z0-9-]*\.([a-zA-Z][a-zA-Z0-9-]*\.)*[a-zA-Z][a-zA-Z0-9-]*[a-zA-Z0-9]$"
        return re.match(pattern, group_id) is not None

    def _verify_gradle(self) -> RepositoryVerificationResult:
        # check if repo contains gradle.properties
        def _extract_group_id_from_properties() -> str | None:
            gradle_properties = self._bfs_walk(Path(self.claimed_repo_fs), "gradle.properties")

            if gradle_properties is None:
                logger.debug("Could not find gradle.properties in the repository: %s", self.claimed_repo_url)
                return None

            properties_lines = gradle_properties.read_text().splitlines()
            for line in properties_lines:
                line_parts = list(filter(None, map(str.strip, line.strip().lower().split("="))))
                if len(line_parts) != 2:
                    continue
                if line_parts[0] == "group":
                    return line_parts[1]

            return None

        def _extract_group_id_from_build_groovy() -> str | None:
            build_gradle = self._bfs_walk(Path(self.claimed_repo_fs), "build.gradle")

            if build_gradle is None:
                logger.debug("Could not find build.gradle in the repository: %s", self.claimed_repo_url)
                return None

            build_gradle_content = build_gradle.read_text()
            for line in build_gradle_content.splitlines():
                line_parts = list(filter(None, map(str.strip, line.strip().lower().split())))
                if len(line_parts) != 2:
                    continue
                if line_parts[0] == "group":
                    group_id = line_parts[1].strip('"').strip("'")
                    if self._is_valid_maven_group_id(group_id):
                        return group_id

            return None

        def _extract_group_id_from_build_kotlin() -> str | None:
            build_gradle = self._bfs_walk(Path(self.claimed_repo_fs), "build.gradle.kts")

            if build_gradle is None:
                logger.debug("Could not find build.gradle.kts in the repository: %s", self.claimed_repo_url)
                return None

            build_gradle_content = build_gradle.read_text()
            for line in build_gradle_content.splitlines():
                line_parts = list(filter(None, map(str.strip, line.strip().lower().split("="))))
                if len(line_parts) != 2:
                    continue
                if line_parts[0] == "group":
                    group_id = line_parts[1].strip('"').strip("'")
                    if self._is_valid_maven_group_id(group_id):
                        return group_id

            return None

        gradle_group_id = _extract_group_id_from_properties()
        if gradle_group_id is None:
            gradle_group_id = _extract_group_id_from_build_groovy()
        if gradle_group_id is None:
            gradle_group_id = _extract_group_id_from_build_kotlin()
        if gradle_group_id is None:
            logger.debug("Could not find group from gradle manifests for %s", self.claimed_repo_url)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.UNKNOWN,
                reason="no_group_in_gradle_manifest",
                build_tool=self.build_tool,
            )

        if not self._same_group(gradle_group_id, self.namespace):
            logger.debug("Group in gradle manifest does not match the provided group id: %s", self.claimed_repo_url)
            return RepositoryVerificationResult(
                status=RepositoryVerificationStatus.FAILED, reason="group_id_mismatch", build_tool=self.build_tool
            )

        return RepositoryVerificationResult(
            status=RepositoryVerificationStatus.PASSED, reason="group_id_match", build_tool=self.build_tool
        )
