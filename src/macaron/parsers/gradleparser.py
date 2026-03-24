# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains helpers for parsing Gradle build configuration files."""

import logging
import re
from pathlib import Path

logger: logging.Logger = logging.getLogger(__name__)


def _extract_assignment_value(file_path: Path, keys: set[str]) -> str | None:
    """Extract an assignment value for a supported key from a Gradle-like file.

    Parameters
    ----------
    file_path : Path
        The file to inspect.
    keys : set[str]
        Accepted key names (for example ``{"group"}`` or ``{"rootProject.name"}``).

    Returns
    -------
    str | None
        The extracted value if a matching ``key = value`` assignment is found;
        otherwise ``None``.
    """
    if not file_path.is_file():
        return None

    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as error:
        logger.debug("Failed to read Gradle file %s: %s", str(file_path), error)
        return None

    assignment_re = re.compile(r"^\s*([A-Za-z0-9_.]+)\s*=\s*(.+?)\s*$")
    for line in lines:
        try:
            match = assignment_re.match(line)
        except re.error as error:
            logger.debug("Failed to apply assignment regex on %s: %s", str(file_path), error)
            continue
        if not match:
            continue

        key = match.group(1).strip()
        if key not in keys:
            continue

        raw_value = match.group(2).strip()
        if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
            raw_value = raw_value[1:-1]
        return raw_value

    return None


def extract_gav_from_gradle_project(project_path: Path) -> tuple[str | None, str | None, str | None]:
    """Extract Gradle coordinates (group, artifact, version) from project files.

    Parameters
    ----------
    project_path : Path
        Path to the root directory of a Gradle project.

    Returns
    -------
    tuple[str | None, str | None, str | None]
        A tuple of ``(group_id, artifact_id, version)`` extracted from common
        Gradle configuration files. Any missing value is returned as ``None``.

    Notes
    -----
    This parser is intentionally lightweight and matches direct ``key = value``
    assignments only. It does not evaluate expressions or variable references.
    """
    group_id = (
        _extract_assignment_value(
            project_path.joinpath("gradle.properties"), {"group", "projectGroup", "projectGroupId"}
        )
        or _extract_assignment_value(project_path.joinpath("build.gradle"), {"group"})
        or _extract_assignment_value(project_path.joinpath("build.gradle.kts"), {"group"})
    )
    artifact_id = (
        _extract_assignment_value(project_path.joinpath("settings.gradle"), {"rootProject.name"})
        or _extract_assignment_value(project_path.joinpath("settings.gradle.kts"), {"rootProject.name"})
        or _extract_assignment_value(project_path.joinpath("gradle.properties"), {"name"})
    )
    version = (
        _extract_assignment_value(project_path.joinpath("gradle.properties"), {"version", "projectVersion"})
        or _extract_assignment_value(project_path.joinpath("build.gradle"), {"version"})
        or _extract_assignment_value(project_path.joinpath("build.gradle.kts"), {"version"})
    )

    if group_id is None:
        logger.debug("Could not find group id in Gradle project: %s", str(project_path))
    if artifact_id is None:
        logger.debug("Could not find artifact id in Gradle project: %s", str(project_path))
    if version is None:
        logger.debug("Could not find version in Gradle project: %s", str(project_path))

    return group_id, artifact_id, version


def gradle_settings_has_modules(settings_path: Path) -> bool:
    """Check whether a Gradle settings file declares one or more modules.

    Parameters
    ----------
    settings_path : Path
        Path to a ``settings.gradle`` or ``settings.gradle.kts`` file.

    Returns
    -------
    bool
        ``True`` when the file contains an ``include`` declaration; otherwise
        ``False``.
    """
    if not settings_path.is_file():
        return False

    try:
        lines = settings_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as error:
        logger.debug("Failed to read Gradle settings file %s: %s", str(settings_path), error)
        return False

    for line in lines:
        stripped = line.strip()
        if re.match(r"^include\s+.+", stripped) or re.match(r"^include\s*\(.+\)", stripped):
            return True

    return False


def extract_included_gradle_modules(settings_path: Path) -> list[str]:
    """Extract module include entries from a Gradle settings file.

    Parameters
    ----------
    settings_path : Path
        Path to a ``settings.gradle`` or ``settings.gradle.kts`` file.

    Returns
    -------
    list[str]
        Ordered list of module paths declared by ``include`` statements.
    """
    if not settings_path.is_file():
        return []

    try:
        lines = settings_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as error:
        logger.debug("Failed to read Gradle settings file %s: %s", str(settings_path), error)
        return []

    modules: list[str] = []
    quoted_value_re = re.compile(r"""['"]([^'"]+)['"]""")
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("include"):
            continue
        modules.extend(match.group(1).strip() for match in quoted_value_re.finditer(stripped) if match.group(1).strip())
    return modules


def find_matching_gradle_module_build_configs(repo_root: Path, artifact_id: str) -> list[Path]:
    """Find module build config files likely associated with the given artifact id.

    Parameters
    ----------
    repo_root : Path
        Root directory of the Gradle repository.
    artifact_id : str
        Expected artifact id.

    Returns
    -------
    list[Path]
        Candidate module build files (for example ``module/build.gradle``)
        associated with the artifact id.
    """

    def _collect_from_settings_paths(settings_paths: list[Path]) -> list[Path]:
        candidates: list[Path] = []
        seen: set[Path] = set()
        for settings_path in settings_paths:
            for module in extract_included_gradle_modules(settings_path):
                module_path = module.strip().strip(":")
                if not module_path:
                    continue
                module_name = module_path.split(":")[-1]
                if artifact_id != module_name and not artifact_id.endswith(f"-{module_name}"):
                    continue
                module_dir = settings_path.parent.joinpath(*module_path.split(":"))
                for build_name in ("build.gradle", "build.gradle.kts"):
                    config_path = module_dir.joinpath(build_name)
                    if config_path.is_file() and config_path not in seen:
                        seen.add(config_path)
                        candidates.append(config_path)
        return candidates

    # Most Gradle multi-module projects declare modules from repository-root
    # settings files, so we try those first as a fast path.
    root_settings_paths = [
        repo_root.joinpath("settings.gradle"),
        repo_root.joinpath("settings.gradle.kts"),
    ]
    root_candidates = _collect_from_settings_paths([p for p in root_settings_paths if p.is_file()])
    if root_candidates:
        return root_candidates

    # Some repos contain independent nested Gradle roots; when root settings do
    # not match the requested artifact, broaden to nested settings files.
    nested_settings_paths = sorted(
        (
            path
            for pattern in ("**/settings.gradle", "**/settings.gradle.kts")
            for path in repo_root.glob(pattern)
            if path not in root_settings_paths
        ),
        key=str,
    )
    return _collect_from_settings_paths(nested_settings_paths)


def find_nearest_modules_gradle_config(
    config_path: Path,
    repo_root: str | Path,
    *,
    max_depth: int = 50,
) -> str | None:
    """Find the nearest ancestor Gradle settings file that defines modules.

    Parameters
    ----------
    config_path : Path
        Path to the starting Gradle configuration file.
    repo_root : str | Path
        Repository root used to bound parent traversal and return a relative path.
    max_depth : int, optional
        Maximum number of parent-directory hops. Defaults to ``50``.

    Returns
    -------
    str | None
        Path to the nearest settings file relative to ``repo_root`` if it
        contains ``include`` declarations. Returns ``None`` otherwise.
    """
    repo_root = Path(repo_root).resolve()
    current_dir = config_path.parent.resolve()
    depth = 0

    while True:
        for settings_name in ("settings.gradle", "settings.gradle.kts"):
            settings_path = current_dir.joinpath(settings_name)
            if gradle_settings_has_modules(settings_path):
                try:
                    return str(settings_path.relative_to(repo_root))
                except ValueError:
                    return None

        if current_dir == repo_root:
            return None

        depth += 1
        if depth > max_depth:
            return None

        parent_dir = current_dir.parent
        if parent_dir == current_dir:
            return None

        current_dir = parent_dir
