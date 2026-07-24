# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This check validates whether a package exists in its public registry and is actively maintained."""

import logging
import urllib.parse
from datetime import UTC, datetime

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
from macaron.slsa_analyzer.package_registry.maven_central_registry import MavenCentralRegistry
from macaron.slsa_analyzer.package_registry.npm_registry import NPMRegistry, find_or_create_npm_asset
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIRegistry, find_or_create_pypi_asset
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)

_REMEDIATION_GENERIC = "Consider replacing or reviewing this dependency as it may no longer be actively maintained."
_REMEDIATION_DEPRECATED = "This package has been explicitly deprecated or removed. Consider replacing this dependency."
_REMEDIATION_ARCHIVED = (
    "The source repository has been archived and is no longer accepting contributions."
    " Consider replacing this dependency."
)


class RegistryMaintainabilityFacts(CheckFacts):
    """The ORM mapping for justifications in the registry maintainability check."""

    __tablename__ = "_registry_maintainability_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)

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

    #: Date string of the most recent release of the package (across all versions).
    last_release_date: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        info={"justification": JustificationType.TEXT},
    )

    #: Number of days elapsed since the most recent release of the package (across all versions).
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

    __mapper_args__ = {  # noqa: RUF012
        "polymorphic_identity": "_registry_maintainability_check",
    }


def _build_registry_url(
    registry_info: PackageRegistryInfo, name: str, namespace: str | None, version: str
) -> str | None:
    """Build a human-facing package page URL for the given registry and package coordinates.

    Parameters
    ----------
    registry_info : PackageRegistryInfo
        The matched package registry information.
    name : str
        The package name.
    namespace : str | None
        The package namespace (used for scoped npm packages, e.g. ``@scope``).
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
        package_name = f"{namespace}/{name}" if namespace else name
        return f"https://www.npmjs.com/package/{package_name}/v/{version}"

    if isinstance(pkg_registry, MavenCentralRegistry) and namespace:
        return f"https://central.sonatype.com/artifact/{namespace}/{name}/{version}"

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
        # A version may have multiple distribution files (.tar.gz, .whl, etc.).
        # Per PEP 592, yanking is tracked per file; we treat the version as yanked
        # if ANY of its files carries the yanked flag.
        version_files = json_extract(pypi_asset.package_json, ["releases", version], list)
        if version_files:
            yanked_files = [f for f in version_files if f.get("yanked")]
            if yanked_files:
                yanked_reason: str | None = yanked_files[0].get("yanked_reason") or None
                return True, yanked_reason
            return False, None

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


def _get_latest_release_timestamp(
    registry_info: PackageRegistryInfo,
    name: str,
    namespace: str | None,
    version: str,
) -> datetime | None:
    """Return the publish timestamp of the *latest* release of the package.

    This is used for the release-recency signal so that a pinned old version of
    an actively maintained package is not incorrectly flagged as unmaintained.

    For PyPI the package-level JSON endpoint already exposes the latest
    version's files under the ``urls`` key, so we reuse the already-cached
    asset.  For npm we resolve the latest version via the registry API and
    then query its publish timestamp via deps.dev.

    Parameters
    ----------
    registry_info : PackageRegistryInfo
        The matched package registry information.
    name : str
        The package name.
    namespace : str | None
        The package namespace (used for scoped npm packages).
    version : str
        The specific version of the analysed PURL, used only as a cache key
        when fetching the PyPI asset.

    Returns
    -------
    datetime | None
        The publish timestamp of the latest release, or ``None`` if it cannot
        be determined.
    """
    pkg_registry = registry_info.package_registry

    if isinstance(pkg_registry, PyPIRegistry):
        pypi_asset = find_or_create_pypi_asset(name, version, registry_info)
        if pypi_asset is None:
            return None
        if not (pypi_asset.package_json or pypi_asset.download(dest="")):
            return None
        upload_time_str = pypi_asset.get_latest_release_upload_time()
        if upload_time_str:
            try:
                # PyPI upload_time strings use "%Y-%m-%dT%H:%M:%S" (no tz suffix); assume UTC.
                return datetime.strptime(upload_time_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
            except ValueError:
                logger.debug("Could not parse PyPI latest release upload time %r.", upload_time_str)
        return None

    if isinstance(pkg_registry, NPMRegistry):
        latest_version = pkg_registry.get_latest_version(namespace, name)
        if latest_version is None:
            logger.debug("Could not determine latest version for npm package %s.", name)
            return None
        latest_purl = str(PackageURL(type="npm", namespace=namespace, name=name, version=latest_version))
        try:
            return pkg_registry.find_publish_timestamp(latest_purl)
        except InvalidHTTPResponseError as error:
            logger.debug("Could not retrieve latest release timestamp for npm package %s: %s", name, error)
        return None

    if isinstance(pkg_registry, MavenCentralRegistry) and namespace:
        try:
            return pkg_registry.find_latest_release_timestamp(namespace, name)
        except InvalidHTTPResponseError as error:
            logger.debug(
                "Could not retrieve latest Maven release timestamp for %s:%s: %s",
                namespace,
                name,
                error,
            )
        return None

    return None


def _check_maven_no_version(
    ctx: AnalyzeContext,
    registry_infos: list[PackageRegistryInfo],
) -> CheckResultData | None:
    """Attempt a release-recency check for a Maven PURL that has no pinned version.

    Maven Central allows querying for the latest release without specifying a
    version, so we can still evaluate release recency even when the caller did
    not pin a specific version in the PURL.

    Parameters
    ----------
    ctx : AnalyzeContext
        The object containing processed data for the target component.
    registry_infos : list[PackageRegistryInfo]
        The package registries available for this analysis run.

    Returns
    -------
    CheckResultData | None
        A ``CheckResultData`` with ``PASSED`` or ``FAILED`` if the latest
        release date can be determined from Maven Central. Returns a
        ``CheckResultData`` with ``UNKNOWN`` when the Maven Central API call
        fails. Returns ``None`` only when this helper is not applicable
        (non-Maven PURL, missing namespace, or no matching registry).
    """
    if ctx.component.type != "maven":
        return None

    parsed_purl = PackageURL.from_string(ctx.component.purl)
    namespace: str | None = parsed_purl.namespace
    if not namespace:
        logger.debug(
            "Maven PURL %s has no namespace; cannot query Maven Central.",
            ctx.component.purl,
        )
        return None

    for _registry_info in registry_infos:
        if _registry_info.ecosystem != "maven":
            continue
        pkg_registry = _registry_info.package_registry
        if not isinstance(pkg_registry, MavenCentralRegistry):
            continue

        registry_url = f"https://central.sonatype.com/artifact/{namespace}/{ctx.component.name}"
        try:
            latest_dt = pkg_registry.find_latest_release_timestamp(namespace, ctx.component.name)
        except InvalidHTTPResponseError as error:
            logger.debug(
                "Could not retrieve latest Maven release for %s: %s",
                ctx.component.purl,
                error,
            )
            registry_name = type(pkg_registry).__name__.replace("Registry", "")
            return CheckResultData(
                result_tables=[
                    RegistryMaintainabilityFacts(
                        registry_name=registry_name,
                        registry_url=registry_url,
                        remediation=("Cannot determine registry status: Maven Central API is unavailable."),
                        confidence=Confidence.LOW,
                    )
                ],
                result_type=CheckResultType.UNKNOWN,
            )

        now = datetime.now(UTC)
        threshold: int = defaults.getint("registry_maintainability", "inactivity_threshold_days", fallback=365)
        days_since_release = (now - latest_dt).days
        last_release_date = latest_dt.strftime("%Y-%m-%d")
        registry_name = type(pkg_registry).__name__.replace("Registry", "")

        if days_since_release > threshold:
            # Apply the same GitHub rescue signal as the versioned path: if the
            # GitHub repo shows recent commit activity, treat the package as
            # still maintained despite the stale Maven Central release.
            # An archived repo is never rescued — it always fails.
            is_archived: bool | None = None
            days_since_commit: int | None = None
            git_service = ctx.dynamic_data.get("git_service")
            if isinstance(git_service, GitHub) and ctx.component.repository:
                repo = ctx.component.repository
                full_name = repo.complete_name.removeprefix("github.com/")
                repo_data = git_service.api_client.get_repo_data(full_name)
                if repo_data:
                    is_archived = bool(repo_data.get("archived", False))
                    if not is_archived:
                        pushed_at: str | None = repo_data.get("pushed_at")
                        if pushed_at:
                            try:
                                commit_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                                days_since_commit = (now - commit_dt).days
                            except ValueError:
                                logger.debug(
                                    "Could not parse pushed_at timestamp %r for %s.",
                                    pushed_at,
                                    ctx.component.purl,
                                )

            if is_archived:
                return CheckResultData(
                    result_tables=[
                        RegistryMaintainabilityFacts(
                            registry_name=registry_name,
                            registry_url=registry_url,
                            days_since_release=days_since_release,
                            last_release_date=last_release_date,
                            is_archived=True,
                            remediation=_REMEDIATION_ARCHIVED,
                            confidence=Confidence.MEDIUM,
                        )
                    ],
                    result_type=CheckResultType.FAILED,
                )

            if days_since_commit is not None and days_since_commit <= threshold:
                return CheckResultData(
                    result_tables=[
                        RegistryMaintainabilityFacts(
                            registry_name=registry_name,
                            registry_url=registry_url,
                            days_since_release=days_since_release,
                            last_release_date=last_release_date,
                            days_since_commit=days_since_commit,
                            confidence=Confidence.MEDIUM,
                        )
                    ],
                    result_type=CheckResultType.PASSED,
                )

            return CheckResultData(
                result_tables=[
                    RegistryMaintainabilityFacts(
                        registry_name=registry_name,
                        registry_url=registry_url,
                        days_since_release=days_since_release,
                        last_release_date=last_release_date,
                        remediation=_REMEDIATION_GENERIC,
                        confidence=Confidence.MEDIUM,
                    )
                ],
                result_type=CheckResultType.FAILED,
            )
        return CheckResultData(
            result_tables=[
                RegistryMaintainabilityFacts(
                    registry_name=registry_name,
                    registry_url=registry_url,
                    days_since_release=days_since_release,
                    last_release_date=last_release_date,
                    confidence=Confidence.MEDIUM,
                )
            ],
            result_type=CheckResultType.PASSED,
        )

    return None


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
        description = "Check if the package exists in its expected public registry and is actively maintained."
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
        # A specific version is required for the full check.  For Maven we can
        # still assess release recency by querying Maven Central for the latest
        # release without a pinned version.
        if not ctx.component.version:
            logger.debug(
                "No version found in PURL %s; attempting Maven-specific recency check.",
                ctx.component.purl,
            )
            registry_infos_nv: list[PackageRegistryInfo] = ctx.dynamic_data["package_registries"]
            maven_no_version_result = _check_maven_no_version(ctx, registry_infos_nv)
            if maven_no_version_result is not None:
                return maven_no_version_result
            return CheckResultData(
                result_tables=[
                    RegistryMaintainabilityFacts(
                        remediation=("Cannot determine registry status: the PURL does not include a specific version."),
                        confidence=Confidence.LOW,
                    )
                ],
                result_type=CheckResultType.UNKNOWN,
            )

        # Iterate over all registries to find one that matches the component ecosystem
        # and can return a publish timestamp.  We skip registries that raise
        # NotImplementedError e.g. Maven Central or InvalidHTTPResponseError.
        registry_infos: list[PackageRegistryInfo] = ctx.dynamic_data["package_registries"]
        matched_registry_info: PackageRegistryInfo | None = None
        publish_dt: datetime | None = None

        for _registry_info in registry_infos:
            if _registry_info.ecosystem != ctx.component.type:
                continue
            try:
                publish_dt = _registry_info.package_registry.find_publish_timestamp(ctx.component.purl)
                matched_registry_info = _registry_info
                break
            except InvalidHTTPResponseError as error:
                logger.debug(
                    "Could not retrieve publish timestamp for %s: %s",
                    ctx.component.purl,
                    error,
                )
            except NotImplementedError:
                continue

        if matched_registry_info is None or publish_dt is None:
            logger.debug(
                "Skipping %s: no matching package registry found for PURL %s.",
                self.check_info.check_id,
                ctx.component.purl,
            )
            return CheckResultData(
                result_tables=[
                    RegistryMaintainabilityFacts(
                        remediation=(
                            "No supported package registry found for this ecosystem "
                            "or the registry API is currently unavailable."
                        ),
                        confidence=Confidence.LOW,
                    )
                ],
                result_type=CheckResultType.UNKNOWN,
            )

        registry_info = matched_registry_info
        pkg_registry = registry_info.package_registry
        registry_name: str = type(pkg_registry).__name__.replace("Registry", "")

        # Extract namespace from the PURL once for reuse across signals.
        parsed_purl = PackageURL.from_string(ctx.component.purl)
        namespace: str | None = parsed_purl.namespace

        now = datetime.now(UTC)

        # Use latest release date of the package for the recency signal.
        latest_publish_dt = _get_latest_release_timestamp(
            registry_info, ctx.component.name, namespace, ctx.component.version
        )
        recency_dt = latest_publish_dt if latest_publish_dt is not None else publish_dt
        days_since_release: int = (now - recency_dt).days
        last_release_date: str = recency_dt.strftime("%Y-%m-%d")

        # Check for explicit deprecation/yanked flag.
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
        threshold: int = defaults.getint("registry_maintainability", "inactivity_threshold_days", fallback=365)

        registry_url = _build_registry_url(registry_info, ctx.component.name, namespace, ctx.component.version)

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
            # If the registry release is stale but the GitHub repo shows recent
            # commit activity, treat the package as still maintained.  This
            # handles mono-repos where one sub-module has not had its own
            # registry release in a while but the project as a whole is active.
            if days_since_commit is not None and days_since_commit <= threshold:
                result_type = CheckResultType.PASSED
                remediation = None
            else:
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
