# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the DockerfileSecurityCheck class with security analysis based on DFScan research."""

import json
import logging
import os
import re
from io import StringIO

from dockerfile_parse import DockerfileParser
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.db_custom_types import DBJsonDict
from macaron.database.table_definitions import CheckFacts
from macaron.json_tools import JsonType
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class DockerfileSecurityFacts(CheckFacts):
    """The ORM mapping for justifications in dockerfile security check."""

    __tablename__ = "_dockerfile_security_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The name of the base image used in the Dockerfile.
    base_image_name: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The version of the base image used in the Dockerfile.
    base_image_version: Mapped[str] = mapped_column(
        String, nullable=False, info={"justification": JustificationType.TEXT}
    )

    #: Security vulnerabilities found in the Dockerfile.
    security_issues: Mapped[dict[str, JsonType]] = mapped_column(
        DBJsonDict, nullable=False, info={"justification": JustificationType.TEXT}
    )

    #: Security risk score (0-100, higher is more risky).
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, info={"justification": JustificationType.TEXT})

    #: Number of security issues found.
    issues_count: Mapped[int] = mapped_column(Integer, nullable=False, info={"justification": JustificationType.TEXT})

    __mapper_args__ = {
        "polymorphic_identity": "dockerfile_security_check",
    }


class DockerfileSecurityAnalyzer:
    """Security analyzer for Dockerfiles based on DFScan research."""

    # Security rules from DFScan research
    RISKY_PORTS = [21, 22, 23, 3306]
    PRIVILEGED_PORTS = list(range(1, 1024))
    SAFE_PRIVILEGED_PORTS = [80, 443]

    SENSITIVE_ENV_KEYWORDS = ["pass", "pswd", "license", "token", "session", "KEY", "AUTHORIZED", "secret"]

    EMAIL_REGEX = re.compile(r"[A-Za-z0-9\u4e00-\u9fa5]+@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+")

    UNSAFE_VOLUMES = [
        "/proc",
        "/",
        "/root/.ssh",
        "/var/run/docker.sock",
        "/var/lib/docker",
        "/etc/docker",
        "Docker.service",
        "Docker.socket",
        "/etc/default/docker",
        "/etc/docker/daemon.JSON",
        "/etc/sysconfig/docker",
        "/usr/bin/containerd",
        "/usr/sbin/runc",
    ]

    SENSITIVE_FILES = [
        "NOTICE",
        "README.md",
        "LICENSE",
        "AUTHORS.md",
        "CONTRIBUTING.md",
        ".vscode/",
        "vendor/",
        "env/",
        "ENV/",
        "build/",
        "dist/",
        "target/",
        "downloads/",
        "eggs/",
        ".eggs/",
        "lib/",
        "lib64/",
        "parts/",
        "sdist/",
        "var/",
        "Dockerfile",
        ".git",
        ".editorconfig",
        "*.egg-info/",
        ".installed.cfg",
        "*.egg",
        "*.manifest",
        "*.spec",
        ".gcloudignore",
        ".gitignore",
        ".tox/",
        ".dockerignore",
        ".coverage",
        ".coverage.*",
        ".cache",
        "htmlcov/",
        "nosetests.xml",
        "coverage.xml",
        "*,cover",
        ".hypothesis/",
        "ssh/",
        "id_rsa",
        ".git-credentials",
        "config.*",
    ]

    SECURITY_CRITICAL_FILES = [
        "id_rsa",
        "id_rsa.pub",
        ".ssh",
        "shadow",
        "/etc/passwd",
        "/etc/group",
        "/etc/profile",
        ".bash_history",
        ".history",
        ".log",
        ".conf",
    ]

    MALICIOUS_RUN_PATTERNS = [
        r">&/dev/tcp/",
        r"&>/dev/tcp",
        r"crontab",
        r"LinEnum\.sh",
        r"mimikatz",
        r"@eval\(\$_POST",
        r"@eval\(\$_GET",
        r"@eval\(\$_REQUEST",
        r"chmod 777",
    ]

    def __init__(self) -> None:
        """Initialize the analyzer."""
        self.issues: list[dict[str, str]] = []
        self.risk_score: int = 0

    def analyze_dockerfile_content(self, dockerfile_content: str) -> tuple[list[dict[str, str]], int, str, str]:
        """
        Analyze Dockerfile content for security issues.

        Parameters
        ----------
        dockerfile_content : str
            Content of the Dockerfile as string

        Returns
        -------
        tuple[list[dict[str, str]], int, str, str]
            tuple of (issues_list, risk_score, base_image_name, base_image_version)
        """
        self.issues = []
        self.risk_score = 0

        base_image_name = "unknown"
        base_image_version = "unknown"

        try:
            # Use dockerfile-parse with fileobj argument
            dockerfile_fileobj = StringIO(dockerfile_content)
            parser = DockerfileParser(fileobj=dockerfile_fileobj)

            # Extract base image info
            base_image_name, base_image_version = self._get_base_image_info(parser)

            # Parse the structure
            structure = parser.structure

            for item in structure:
                instruction_type = item.get("instruction", "").upper()
                instruction_value = item.get("value", "")

                if instruction_type == "FROM":
                    self._check_from_instruction(instruction_value)
                elif instruction_type == "USER":
                    self._check_user_instruction(instruction_value)
                elif instruction_type == "EXPOSE":
                    self._check_expose_instruction(instruction_value)
                elif instruction_type == "ENV":
                    self._check_env_instruction(instruction_value)
                elif instruction_type == "VOLUME":
                    self._check_volume_instruction(instruction_value)
                elif instruction_type == "COPY":
                    self._check_copy_instruction(instruction_value)
                elif instruction_type == "ADD":
                    self._check_add_instruction(instruction_value)
                elif instruction_type == "RUN":
                    self._check_run_instruction(instruction_value)

        except json.JSONDecodeError as e:
            logger.error("Error parsing Dockerfile: %s", e)
            self._add_issue("ERROR", "PARSE", f"Failed to parse Dockerfile: {str(e)}", 5)

        return self.issues, self.risk_score, base_image_name, base_image_version

    def _get_base_image_info(self, parser: DockerfileParser) -> tuple[str, str]:
        """
        Extract base image name and version from DockerfileParser.

        Parameters
        ----------
        parser : DockerfileParser
            The dockerfile parser instance

        Returns
        -------
        tuple[str, str]
            tuple of (image_name, image_version)
        """
        try:
            # Get the base image
            base_image = parser.baseimage
            if base_image:
                # Split image name and tag
                if ":" in base_image:
                    image_name, image_version = base_image.split(":", 1)
                else:
                    image_name = base_image
                    image_version = "latest"
                return image_name, image_version

        except AttributeError as e:
            logger.debug("Error extracting base image info: %s", e)

        return "unknown", "unknown"

    def _add_issue(self, severity: str, instruction: str, issue: str, risk_points: int = 0) -> None:
        """Add a security issue to the results."""
        self.issues.append(
            {"severity": severity, "instruction": instruction, "issue": issue, "risk_points": str(risk_points)}
        )
        self.risk_score += risk_points

    def _check_from_instruction(self, content: str) -> None:
        """Check FROM instruction for security issues."""
        # Extract image name and tag
        image_parts = content.split(":")
        image_name = image_parts[0]
        tag = image_parts[1] if len(image_parts) > 1 else "latest"

        # Check for latest tag usage
        if tag == "latest" or len(image_parts) == 1:
            self._add_issue(
                "MEDIUM", "FROM", f"Using 'latest' tag or no tag specified for base image: {image_name}", 15
            )

        # Check for old base image (simplified - would need Docker Hub API integration)
        self._check_base_image_age(image_name, tag)

    def _check_base_image_age(self, image_name: str, tag: str) -> None:
        """Check if base image is too old (simplified implementation)."""
        try:
            # This would require Docker Hub API integration
            # For now, just warn about common old tags
            old_patterns = ["ubuntu:14.04", "ubuntu:16.04", "centos:6", "centos:7", "python:2.7"]
            full_image = f"{image_name}:{tag}"

            for old_pattern in old_patterns:
                if old_pattern in full_image:
                    self._add_issue("HIGH", "FROM", f"Using potentially outdated base image: {full_image}", 25)
                    break
        except AttributeError as e:
            logger.debug("Error checking base image age: %s", e)

    def _check_user_instruction(self, content: str) -> None:
        """Check USER instruction for root usage."""
        if content.strip().lower() in {"root", "0"}:
            self._add_issue("HIGH", "USER", "Running container as root user poses security risks", 30)

    def _check_expose_instruction(self, content: str) -> None:
        """Check EXPOSE instruction for risky ports."""
        try:
            # Handle both space-separated and single port formats
            port_strings = content.split()
            ports: list[int] = []

            for port_str in port_strings:
                # Handle port ranges and protocols (e.g., "8080/tcp")
                port_str = port_str.split("/")[0]  # Remove protocol if present
                if "-" in port_str:
                    # Handle port ranges
                    start_port, end_port = port_str.split("-")
                    ports.extend(range(int(start_port), int(end_port) + 1))
                else:
                    ports.append(int(port_str))

            for port in ports:
                if port in self.RISKY_PORTS:
                    self._add_issue("HIGH", "EXPOSE", f"Exposing risky port {port} (SSH/FTP/MySQL/Telnet)", 25)
                elif port in self.PRIVILEGED_PORTS and port not in self.SAFE_PRIVILEGED_PORTS:
                    self._add_issue("MEDIUM", "EXPOSE", f"Exposing privileged port {port}", 15)
        except (ValueError, AttributeError) as e:
            logger.debug("Could not parse ports from EXPOSE instruction: %s", e)

    def _check_env_instruction(self, content: str) -> None:
        """Check ENV instruction for sensitive information."""
        # Check for sensitive keywords
        content_lower = content.lower()
        for keyword in self.SENSITIVE_ENV_KEYWORDS:
            if keyword.lower() in content_lower:
                self._add_issue(
                    "HIGH", "ENV", f"Potentially sensitive information in environment variable: {keyword}", 20
                )

        # Check for email addresses
        if self.EMAIL_REGEX.search(content):
            self._add_issue("MEDIUM", "ENV", "Email address found in environment variable", 10)

    def _check_volume_instruction(self, content: str) -> None:
        """Check VOLUME instruction for unsafe mounts."""
        # Parse volume instruction - can be JSON array or space-separated
        volumes = []

        if content.strip().startswith("["):
            # JSON array format
            try:
                volumes = json.loads(content)
            except json.JSONDecodeError:
                # Fallback to string parsing
                volumes = [v.strip().strip("\"'") for v in content.strip("[]").split(",")]
        else:
            # Space-separated format
            volumes = [v.strip().strip("\"'") for v in content.split()]

        for volume in volumes:
            for unsafe_vol in self.UNSAFE_VOLUMES:
                if volume == unsafe_vol or volume.startswith(unsafe_vol):
                    self._add_issue("CRITICAL", "VOLUME", f"Unsafe volume mount detected: {volume}", 40)

    def _check_copy_instruction(self, content: str) -> None:
        """Check COPY instruction for sensitive files."""
        # Parse COPY instruction arguments
        parts = content.split()
        if not parts:
            return

        # COPY can have multiple sources, last argument is destination
        sources = parts[:-1] if len(parts) > 1 else parts

        for source in sources:
            # Check for wildcard usage
            if source == ".":
                self._add_issue(
                    "MEDIUM", "COPY", "Using '.' as source copies entire build context including sensitive files", 15
                )

            # Check for sensitive files
            self._check_file_sensitivity("COPY", source)

    def _check_add_instruction(self, content: str) -> None:
        """Check ADD instruction for security issues."""
        parts = content.split()
        if not parts:
            return

        # ADD can have multiple sources, last argument is destination
        sources = parts[:-1] if len(parts) > 1 else parts

        for source in sources:
            # Check for URL usage
            if source.startswith(("http://", "https://", "ftp://")):
                self._add_issue("HIGH", "ADD", f"ADD instruction downloading from URL: {source}", 25)

            # Check for compressed files
            if any(source.endswith(ext) for ext in [".tar", ".tar.gz", ".tgz", ".zip"]):
                self._add_issue("MEDIUM", "ADD", f"ADD instruction with compressed file: {source}", 15)

            # Same checks as COPY
            if source == ".":
                self._add_issue(
                    "MEDIUM", "ADD", "Using '.' as source copies entire build context including sensitive files", 15
                )

            self._check_file_sensitivity("ADD", source)

    def _check_file_sensitivity(self, instruction: str, filepath: str) -> None:
        """Check if file path contains sensitive information."""
        for sensitive_file in self.SENSITIVE_FILES:
            if sensitive_file in filepath:
                self._add_issue("MEDIUM", instruction, f"Potentially sensitive file being copied: {filepath}", 10)
                break

        for critical_file in self.SECURITY_CRITICAL_FILES:
            if critical_file in filepath:
                self._add_issue("CRITICAL", instruction, f"Security-critical file being copied: {filepath}", 35)
                break

    def _check_run_instruction(self, content: str) -> None:
        """Check RUN instruction for malicious commands."""
        for pattern in self.MALICIOUS_RUN_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                self._add_issue("CRITICAL", "RUN", f"Potentially malicious command detected: {pattern}", 40)


class DockerfileSecurityCheck(BaseCheck):
    """This check analyzes Dockerfiles for security vulnerabilities based on DFScan research."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_dockerfile_security_1"
        description = """This check analyzes Dockerfiles for security vulnerabilities and best practices
        based on DFScan research findings. It examines Docker instructions for potential security risks
        including root user usage, risky port exposure, sensitive information leakage, unsafe volume mounts,
        and malicious commands."""
        depends_on: list[tuple[str, CheckResultType]] = []
        eval_reqs = [ReqName.SCRIPTED_BUILD]
        super().__init__(
            check_id=check_id,
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.FAILED,
        )

    def run_check(self, ctx: AnalyzeContext) -> CheckResultData:
        """
        Implement the check in this method.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.

        Returns
        -------
        CheckResultData
            The result of the check.
        """
        result_tables: list[CheckFacts] = []

        try:
            # Find and read Dockerfile content
            dockerfile_content = self._get_dockerfile_content(ctx)
            if not dockerfile_content:
                logger.debug("No Dockerfile found in repository")
                return CheckResultData(result_tables=result_tables, result_type=CheckResultType.FAILED)

            # Analyze the Dockerfile
            analyzer = DockerfileSecurityAnalyzer()
            issues, risk_score, base_image_name, base_image_version = analyzer.analyze_dockerfile_content(
                dockerfile_content
            )

            # Determine confidence and result type based on risk score and issues
            if risk_score >= 100:
                result_type = CheckResultType.FAILED
                confidence = Confidence.HIGH
            elif risk_score >= 50:
                result_type = CheckResultType.FAILED
                confidence = Confidence.MEDIUM
            elif risk_score > 0:
                result_type = CheckResultType.PASSED
                confidence = Confidence.MEDIUM
            else:
                result_type = CheckResultType.PASSED
                confidence = Confidence.HIGH

            # Create detailed security issues dictionary
            security_issues_dict = {
                "total_issues": len(issues),
                "risk_score": risk_score,
                "issues_by_severity": {},
                "issues_by_instruction": {},
                "detailed_issues": issues,
            }

            # Group issues by severity and instruction
            for issue in issues:
                severity = issue.get("severity", "UNKNOWN")
                instruction = issue.get("instruction", "UNKNOWN")

                # Ensure the dicts are actually dicts before using 'in'
                if not isinstance(security_issues_dict.get("issues_by_severity"), dict):
                    security_issues_dict["issues_by_severity"] = {}
                if not isinstance(security_issues_dict.get("issues_by_instruction"), dict):
                    security_issues_dict["issues_by_instruction"] = {}

                issues_by_severity = security_issues_dict.get("issues_by_severity")
                issues_by_instruction = security_issues_dict.get("issues_by_instruction")

                if not isinstance(issues_by_severity, dict):
                    issues_by_severity = {}
                    security_issues_dict["issues_by_severity"] = issues_by_severity
                if not isinstance(issues_by_instruction, dict):
                    issues_by_instruction = {}
                    security_issues_dict["issues_by_instruction"] = issues_by_instruction

                if severity not in issues_by_severity:
                    issues_by_severity[severity] = 0
                issues_by_severity[severity] += 1

                if instruction not in issues_by_instruction:
                    issues_by_instruction[instruction] = 0
                issues_by_instruction[instruction] += 1

            # Create facts
            facts = DockerfileSecurityFacts(
                base_image_name=base_image_name,
                base_image_version=base_image_version,
                security_issues=security_issues_dict,
                risk_score=risk_score,
                issues_count=len(issues),
                confidence=confidence,
            )

            result_tables.append(facts)

            return CheckResultData(
                result_tables=result_tables,
                result_type=result_type,
            )

        except (OSError, ValueError) as e:
            logger.error("Error processing Dockerfile security check: %s", e)
            return CheckResultData(result_tables=result_tables, result_type=CheckResultType.UNKNOWN)

    def _get_dockerfile_content(self, ctx: AnalyzeContext) -> str | None:
        """
        Get Dockerfile content from the repository.

        Parameters
        ----------
        ctx : AnalyzeContext
            The analyze context containing repository information

        Returns
        -------
        Optional[str]
            The Dockerfile content as string, or None if not found
        """
        # Try different ways to get the repository path
        repo_path = None

        # Method 1: Check if there's a component with repository info
        if hasattr(ctx, "component") and ctx.component:
            if hasattr(ctx.component, "repository") and ctx.component.repository:
                if hasattr(ctx.component.repository, "fs_path"):
                    repo_path = ctx.component.repository.fs_path
                    logger.debug("Found repo_path via component.repository.fs_path: %s", repo_path)

        # Common Dockerfile names
        dockerfile_names = ["Dockerfile", "dockerfile", "Dockerfile.prod", "Dockerfile.dev"]

        # Ensure repo_path is not None before proceeding
        if repo_path is None:
            logger.debug("repo_path is None, cannot search for Dockerfile.")
            return None

        # Check root directory first
        for dockerfile_name in dockerfile_names:
            dockerfile_path = os.path.join(repo_path, dockerfile_name)
            if os.path.exists(dockerfile_path):
                try:
                    with open(dockerfile_path, encoding="utf-8") as f:
                        content = f.read()
                        logger.info("Found Dockerfile at: %s", dockerfile_path)
                        return content
                except (OSError, UnicodeDecodeError) as e:
                    logger.debug("Error reading Dockerfile %s: %s", dockerfile_path, e)

        # Search recursively for Dockerfiles (limit depth to avoid deep recursion)
        max_depth = 3
        for root, dirs, files in os.walk(repo_path):
            # Calculate current depth
            depth = root[len(repo_path) :].count(os.sep)
            if depth >= max_depth:
                dirs[:] = []  # Don't recurse deeper
                continue

            # Skip hidden directories and common non-source directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["node_modules", "venv", "env"]]

            for file in files:
                if file.lower().startswith("dockerfile"):
                    dockerfile_path = os.path.join(root, file)
                    try:
                        with open(dockerfile_path, encoding="utf-8") as f:
                            content = f.read()
                            logger.info("Found Dockerfile at: %s", dockerfile_path)
                            return content
                    except (OSError, UnicodeDecodeError) as e:
                        logger.debug("Error reading Dockerfile %s: %s", dockerfile_path, e)

        logger.info("No Dockerfile found in repository at path: %s", repo_path)
        return None


registry.register(DockerfileSecurityCheck())
