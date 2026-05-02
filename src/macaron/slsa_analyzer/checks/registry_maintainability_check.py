# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This check validates whether a package exists in its public registry and is actively maintained."""

import logging
import urllib.parse
from datetime import datetime, timezone

from packageurl import PackageURL
from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.config.defaults import defaults
from macaron.database.table_definitions import CheckFacts
from macaron.errors import InvalidHTTPResponseError
from macaron.json_tools import json_extract
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import (
    CheckResultData,
    CheckResultType,
    Confidence,
    JustificationType,
)
from macaron.slsa_analyzer.git_service.github import GitHub
from macaron.slsa_analyzer.package_registry.npm_registry import NPMRegistry, find_or_create_npm_asset
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIRegistry, find_or_create_pypi_asset
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)

_REMEDIATION_GENERIC = (
    "Consider replacing or reviewing this dependency as it may no longer be actively maintained."
)
_REMEDIATION_DEPRECATED = (
    "This package has been explicitly deprecated or removed. Consider replacing this dependency."
)
_REMEDIATION_ARCHIVED = (
    "The source repository has been archived and is no longer accepting contributions."
    " Consider replacing this dependency."
)


class RegistryMaintainabilityFacts(CheckFacts):
    """The ORM mapping for justifications in the registry maintainability check."""

    __tablename__ = "_registry_maintainability_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The name of the matched package registry (e.g. PyPI, npm).
    registry_name: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        info={"justification": JustificationType.TEXT},
    )

    #: A human-facing link to the package page on the registry.
    registry_url: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        info={"justification": JustificationType.HREF},
    )

    #: A link to the source repository (GitHub), if available.
    repository_url: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        info={"justification": JustificationType.HREF},
    )

    #: Date string of the most recent release.
    last_release_date: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        info={"justification": JustificationType.TEXT},
    )

    #: Number of days elapsed since the most recent release.
    days_since_release: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        info={"justification": JustificationType.TEXT},
    )

    #: Whether the package version is explicitly deprecated or yanked.
    is_deprecated: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        info={"justification": JustificationType.TEXT},
    )

    #: Human-readable reason provided by the registry for the deprecation or yank.
    deprecation_reason: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        info={"justification": JustificationType.TEXT},
    )

    #: Whether the source repository is archived (GitHub only).
    is_archived: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        info={"justification": JustificationType.TEXT},
    )

    #: Date string of the most recent push to the source repository (GitHub only).
    last_commit_date: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        info={"justification": JustificationType.TEXT},
    )

    #: Number of days elapsed since the most recent push to the source repository (GitHub only).
    days_since_commit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        info={"justification": JustificationType.TEXT},
    )

    #: Suggested remediation action for the user.
    remediation: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        info={"justification": JustificationType.TEXT},
    )

    __mapper_args__ = {
        "polymorphic_identity": "_registry_maintainability_check",
    }


def _build_registry_url(registry_info: PackageRegistryInfo, name: str, version: str) -> str | None:
    """Build a human-facing package page URL for the given registry and package coordinates.

    Parameters
    ----------
    registry_info : PackageRegistryInfo
        The matched package registry information.
    name : str
        The package name.
    version : str
        The package version.

    Returns
    -------
    str | None
        The human-facing URL, or ``None`` if the registry type is unsupported.
    """
    pkg_registry = registry_info.package_registry

    if isinstance(pkg_registry, PyPIRegistry) and pkg_registry.registry_url:
        return urllib.parse.urljoin(pkg_registry.registry_url, f"project/{name}/{version}/")

    if isinstance(pkg_registry, NPMRegistry):
        return f"https://www.npmjs.com/package/{name}/v/{version}"

    return None


def _check_deprecated(
    registry_info: PackageRegistryInfo,
    name: str,
    namespace: str | None,
    version: str,
) -> tuple[bool | None, str | None]:
    """Check whether the package version is explicitly deprecated or yanked.

    The check is ecosystem-specific:

    * **PyPI**: inspects the ``yanked`` flag in the release metadata for the
      specific version (``releases[version][i]["yanked"]``).
    * **npm**: inspects the top-level ``deprecated`` field in the version
      manifest returned by the registry.
    * **Other ecosystems**: returns ``(None, None)`` — signal not available.

    Parameters
    ----------
    registry_info : PackageRegistryInfo
        The matched package registry information.
    name : str
        The package name.
    namespace : str | None
        The package namespace (used for scoped npm packages).
    version : str
        The package version.

    Returns
    -------
    tuple[bool | None, str | None]
        A tuple ``(is_deprecated, reason)``.  When the signal is not available
        for the current ecosystem both values are ``None``.
    """
    pkg_registry = registry_info.package_registry

    if isinstance(pkg_registry, PyPIRegistry):
        pypi_asset = find_or_create_pypi_asset(name, version, registry_info)
        if pypi_asset is None:
            logger.debug("Could not obtain PyPI package JSON asset for %s@%s.", name, version)
            return None, None

        if not (pypi_asset.package_json or pypi_asset.download(dest="")):
            logger.debug("Failed to download PyPI package JSON for %s@%s.", name, version)
            return None, None

        # The package-level endpoint stores per-version file info under ``releases``.
        version_files = json_extract(pypi_asset.package_json, ["releases", version], list)
        if version_files:
            yanked: bool = bool(version_files[0].get("yanked", False))
            yanked_reason: str | None = version_files[0].get("yanked_reason") or None
            return yanked, yanked_reason

        return False, None

    if isinstance(pkg_registry, NPMRegistry):
        npm_asset = find_or_create_npm_asset(name, namespace, version, registry_info)
        if npm_asset is None:
            logger.debug("Could not obtain npm package JSON asset for %s@%s.", name, version)
            return None, None

        if not (npm_asset.package_json or npm_asset.download(dest="")):
            logger.debug("Failed to download npm package JSON for %s@%s.", name, version)
            return None, None

        deprecated_msg = npm_asset.package_json.get("deprecated")
        if deprecated_msg:
            return True, str(deprecated_msg)
        return False, None

    # Maven Central and other ecosystems do not expose a standard deprecation flag.
    return None, None


class RegistryMaintainabilityCheck(BaseCheck):
    """Check whether a package exists in its public registry and is actively maintained.

    The check evaluates three independent signals when available:

    1. **Registry presence and release recency** — the package must be found on
       its expected public registry, and the most recent release must fall within
       the configured inactivity threshold (``inactivity_threshold_days``).
    2. **Deprecated / yanked status** — PyPI yanked releases and npm deprecated
       packages cause an immediate failure regardless of release age.
    3. **Source repository archived status and commit recency** — when the
       component's source repository is hosted on GitHub, the check also
       inspects whether the repository has been archived and how recently code
       was pushed.

    The check returns ``UNKNOWN`` when it cannot determine a result (e.g.
    unsupported ecosystem, no version in PURL, or an API error).
    """

    def __init__(self) -> None:
        """Initialize the check instance."""
        check_id = "mcn_registry_maintainability_1"
        description = (
            "Check if the package exists in its expected public registry "
            "and is actively maintained."
        )
        super().__init__(check_id=check_id, description=description)

    def run_check(self, ctx: AnalyzeContext) -> CheckResultData:
        """Run the registry maintainability check.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target component.

        Returns
        -------
        CheckResultData
            The result of the check.
        """
        # A specific version is required to query the registry.
        if not ctx.component.version:
            logger.debug(
                "Skipping %s: no version found in PURL %s.",
                self.check_info.check_id,
                ctx.component.purl,
            )
            return CheckResultData(
                result_tables=[
                    RegistryMaintainabilityFacts(
                        remediation=(
                            "Cannot determine registry status: "
                            "the PURL does not include a specific version."
                        ),
                        confidence=Confidence.LOW,
                    )
                ],
                result_type=CheckResultType.UNKNOWN,
            )

        # At least one registry must be matched for this ecosystem.
        registry_infos: list[PackageRegistryInfo] = ctx.dynamic_data["package_registries"]
        if not registry_infos:
            logger.debug(
                "Skipping %s: no package registries found for PURL %s.",
                self.check_info.check_id,
                ctx.component.purl,
            )
            return CheckResultData(
                result_tables=[
                    RegistryMaintainabilityFacts(
                        remediation="No supported package registry found for this ecosystem.",
                        confidence=Confidence.LOW,
                    )
                ],
                result_type=CheckResultType.UNKNOWN,
            )

        registry_info = registry_infos[0]
        pkg_registry = registry_info.package_registry
        registry_name: str = type(pkg_registry).__name__.replace("Registry", "")

        # Confirm registry presence and retrieve last release date.
        try:
            publish_dt: datetime = registry_info.package_registry.find_publish_timestamp(
                ctx.component.purl
            )
        except InvalidHTTPResponseError as error:
            logger.debug(
                "Could not retrieve publish timestamp for %s: %s",
                ctx.component.purl,
                error,
            )
            return CheckResultData(
                result_tables=[
                    RegistryMaintainabilityFacts(
                        registry_name=registry_name,
                        registry_url=_build_registry_url(
                            registry_info, ctx.component.name, ctx.component.version
                        ),
                        remediation=(
                            "The package could not be found on the registry or the registry "
                            "API is currently unavailable."
                        ),
                        confidence=Confidence.LOW,
                    )
                ],
                result_type=CheckResultType.UNKNOWN,
            )

        now = datetime.now(timezone.utc)
        days_since_release: int = (now - publish_dt).days
        last_release_date: str = publish_dt.strftime("%Y-%m-%d")

        # Check for explicit deprecation / yanked flag.
        parsed_purl = PackageURL.from_string(ctx.component.purl)
        namespace: str | None = parsed_purl.namespace

        is_deprecated, deprecation_reason = _check_deprecated(
            registry_info,
            ctx.component.name,
            namespace,
            ctx.component.version,
        )

        # Retrieve GitHub signals (archived status + last commit).
        is_archived: bool | None = None
        last_commit_date: str | None = None
        days_since_commit: int | None = None
        repository_url: str | None = None

        git_service = ctx.dynamic_data.get("git_service")
        if isinstance(git_service, GitHub) and ctx.component.repository:
            repo = ctx.component.repository
            full_name = repo.complete_name.removeprefix("github.com/")
            repo_data = git_service.api_client.get_repo_data(full_name)

            if repo_data:
                is_archived = bool(repo_data.get("archived", False))
                pushed_at: str | None = repo_data.get("pushed_at")
                if pushed_at:
                    # GitHub timestamps use the ``Z`` suffix; normalise for datetime.fromisoformat() on Python < 3.11.
                    try:
                        commit_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                        days_since_commit = (now - commit_dt).days
                        last_commit_date = commit_dt.strftime("%Y-%m-%d")
                    except ValueError:
                        logger.debug(
                            "Could not parse pushed_at timestamp %r for %s; skipping commit signal.",
                            pushed_at,
                            ctx.component.purl,
                        )
                repository_url = f"https://github.com/{full_name}"
        else:
            logger.debug(
                "GitHub signals not available for %s: git service is not GitHub or no repository.",
                ctx.component.purl,
            )

        # Determine result based on collected signals.
        threshold: int = defaults.getint(
            "registry_maintainability", "inactivity_threshold_days", fallback=365
        )

        registry_url = _build_registry_url(
            registry_info, ctx.component.name, ctx.component.version
        )

        result_type: CheckResultType
        remediation: str | None

        if is_archived:
            result_type = CheckResultType.FAILED
            remediation = _REMEDIATION_ARCHIVED
        elif is_deprecated:
            reason_suffix = f": {deprecation_reason}" if deprecation_reason else "."
            remediation = _REMEDIATION_DEPRECATED + reason_suffix
            result_type = CheckResultType.FAILED
        elif days_since_release > threshold:
            result_type = CheckResultType.FAILED
            remediation = _REMEDIATION_GENERIC
        elif days_since_commit is not None and days_since_commit > threshold:
            result_type = CheckResultType.FAILED
            remediation = _REMEDIATION_GENERIC
        else:
            result_type = CheckResultType.PASSED
            remediation = None

        # Confidence is HIGH when we have definitive signals. Downgrade to MEDIUM
        # when only the release-date signal is available (no GitHub API / deprecated flag).
        if days_since_commit is not None or is_deprecated is not None:
            confidence = Confidence.HIGH
        else:
            confidence = Confidence.MEDIUM

        return CheckResultData(
            result_tables=[
                RegistryMaintainabilityFacts(
                    registry_name=registry_name,
                    registry_url=registry_url,
                    repository_url=repository_url,
                    last_release_date=last_release_date,
                    days_since_release=days_since_release,
                    is_deprecated=is_deprecated,
                    deprecation_reason=deprecation_reason,
                    is_archived=is_archived,
                    last_commit_date=last_commit_date,
                    days_since_commit=days_since_commit,
                    remediation=remediation,
                    confidence=confidence,
                )
            ],
            result_type=result_type,
        )


registry.register(RegistryMaintainabilityCheck())
