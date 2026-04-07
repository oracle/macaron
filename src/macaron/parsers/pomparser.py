# Copyright (c) 2024 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the parser for POM files."""

import logging
import os
from pathlib import Path
from xml.etree.ElementTree import Element  # nosec B405

import defusedxml.ElementTree
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

logger: logging.Logger = logging.getLogger(__name__)


def _read_pom_text(pom_path: Path) -> str | None:
    """Read a POM file with a tolerant decoding strategy.

    Maven projects in the wild may contain POM files encoded as legacy
    single-byte encodings instead of UTF-8. For parser robustness we try
    UTF-8 first and then fall back to Latin-1.

    References
    ----------
    * Python codec behavior for Latin-1 mapping bytes 0x00..0xFF directly:
      https://docs.python.org/3.11/library/codecs.html
    """
    try:
        pom_bytes = pom_path.read_bytes()
    except OSError as error:
        logger.debug(error)
        return None

    try:
        return pom_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return pom_bytes.decode("latin-1")
        except UnicodeDecodeError as error:
            logger.debug("Failed to decode pom.xml %s: %s", pom_path, error)
            return None


def _tag_matches(tag: str, local_name: str) -> bool:
    """Return whether an XML tag matches a local name with/without namespace."""
    return tag == local_name or tag.endswith("}" + local_name)


def _find_child(elem: Element, local_name: str) -> Element | None:
    """Find a direct child element by local tag name."""
    return next((ch for ch in elem if _tag_matches(ch.tag, local_name)), None)


def _find_child_text(parent: Element, local_name: str) -> str | None:
    """Find direct child text by local tag name."""
    elem = _find_child(parent, local_name)
    if elem is None or not elem.text:
        return None
    return elem.text.strip()


def parse_pom_string(pom_string: str) -> Element | None:
    """
    Parse the passed POM string using defusedxml.

    Parameters
    ----------
    pom_string : str
        The contents of a POM file as a string.

    Returns
    -------
    Element | None
        The parsed element representing the POM's XML hierarchy.
    """
    try:
        # Stored here first to help with type checking.
        pom: Element = fromstring(pom_string)
        return pom
    except defusedxml.ElementTree.ParseError as error:
        logger.debug("Failed to parse XML: %s", error)
    except DefusedXmlException as error:
        logger.debug("POM rejected due to possible security issues: %s", error)
    return None


def extract_gav_from_pom(pom_file: Path) -> tuple[str | None, str | None, str | None]:
    """
    Extract Maven coordinates (groupId, artifactId, version) from a `pom.xml`.

    The function reads and parses the POM and attempts to extract the
    `<groupId>`, `<artifactId>`, and `<version>` values from the root `<project>`
    element. If an individual coordinate cannot be found, that field is returned
    as ``None``. If the POM cannot be parsed at all, all three values are
    returned as ``None``.

    If `<groupId>` is not present directly under `<project>`, the function falls
    back to `<project>/<parent>/<groupId>`.

    Parameters
    ----------
    pom_file : pathlib.Path
        Path to the `pom.xml` file to parse.

    Returns
    -------
    group_id : str | None
        The Maven `groupId` if found; otherwise ``None``.
    artifact_id : str | None
        The Maven `artifactId` if found; otherwise ``None``.
    version : str | None
        The Maven `version` if found; otherwise ``None``.

    Notes
    -----
    * This function does not resolve property-substituted values (e.g.,
      ``${project.version}``).
    * XML namespaces are handled by matching tag suffixes (e.g., ``...}groupId``).
    """
    pom_content = _read_pom_text(pom_file)
    if pom_content is None:
        logger.debug("Could not read pom.xml: %s", str(pom_file))
        return None, None, None

    pom_root = parse_pom_string(pom_content)

    if pom_root is None:
        logger.debug("Could not parse pom.xml: %s", str(pom_file))
        return None, None, None

    # Direct project coordinates
    group_id = _find_child_text(pom_root, "groupId")
    artifact_id = _find_child_text(pom_root, "artifactId")
    version = _find_child_text(pom_root, "version")

    # Fallback: groupId may be inherited from parent
    if group_id is None:
        parent_elem = _find_child(pom_root, "parent")
        if parent_elem is not None:
            group_id = _find_child_text(parent_elem, "groupId")

    if group_id is None:
        logger.debug("Could not find groupId in pom.xml (project or parent): %s", str(pom_file))
    if artifact_id is None:
        logger.debug("Could not find artifactId in pom.xml: %s", str(pom_file))
    if version is None:
        logger.debug("Could not find version in pom.xml: %s", str(pom_file))

    return group_id, artifact_id, version


def detect_parent_pom(pom_path: Path, repo_root: str | Path) -> str | None:
    """Detect a parent POM file for a given `pom.xml` if it exists in the repo.

    This inspects the `<parent>` section of the POM and resolves the parent POM
    file path using Maven semantics:

    * If `<project>/<parent>/<relativePath>` is present and non-empty, that path
      (relative to the directory containing `pom.xml`) is used.
    * Otherwise Maven defaults to ``../pom.xml``.

    See https://maven.apache.org/ref/3.0/maven-model/maven.html#class_parent.

    If the resolved parent POM exists on disk and is within `repo_root`, this
    returns its path relative to `repo_root`. Otherwise returns ``None``.

    Parameters
    ----------
    pom_path : Path
        Path to the child `pom.xml`.
    repo_root : str | Path
        Repository root path used to produce a repo-relative return value.

    Returns
    -------
    parent_pom : str | None
        Repo-relative path to the parent `pom.xml` if found; otherwise ``None``.
    """
    repo_root = Path(repo_root)

    pom_content = _read_pom_text(pom_path)
    if pom_content is None:
        return None

    pom_root = parse_pom_string(pom_content)
    if pom_root is None:
        return None

    parent_elem = _find_child(pom_root, "parent")
    if parent_elem is None:
        return None

    rel_path_elem = _find_child(parent_elem, "relativePath")
    # Maven default is ../pom.xml if relativePath is absent or empty
    relative_path = (
        rel_path_elem.text.strip()
        if (rel_path_elem is not None and rel_path_elem.text and rel_path_elem.text.strip())
        else os.path.join("../")
    )

    parent_candidate = Path(pom_path.parent, relative_path, "pom.xml").resolve()
    if not parent_candidate.is_file():
        return None

    # Ensure it is inside the repo (avoid returning paths outside repo_root)
    try:
        return str(parent_candidate.relative_to(repo_root))
    except ValueError:
        return None


def pom_has_modules(pom_path: Path) -> bool:
    """Check whether a POM contains a non-empty ``<modules>`` section.

    This function parses the POM and returns ``True`` if it finds at least one
    ``<module>`` entry under ``<modules>`` (i.e., the POM is an aggregator/reactor
    POM).

    Parameters
    ----------
    pom_path : Path
        Path to the ``pom.xml`` to inspect.

    Returns
    -------
    bool
        ``True`` if the POM has a ``<modules><module>...`` entry; otherwise
        ``False``.
    """
    pom_content = _read_pom_text(pom_path)
    if pom_content is None:
        return False

    pom_root = parse_pom_string(pom_content)
    if pom_root is None:
        return False

    modules_elem = _find_child(pom_root, "modules")
    if modules_elem is None:
        return False

    return any(_tag_matches(ch.tag, "module") and ch.text and ch.text.strip() for ch in modules_elem)


def extract_included_pom_modules(pom_path: Path) -> list[str]:
    """Extract module entries from a Maven ``pom.xml``.

    Parameters
    ----------
    pom_path : Path
        Path to the ``pom.xml`` file to inspect.

    Returns
    -------
    list[str]
        Ordered list of non-empty module paths declared under
        ``<project><modules><module>...``.
    """
    pom_content = _read_pom_text(pom_path)
    if pom_content is None:
        return []

    pom_root = parse_pom_string(pom_content)
    if pom_root is None:
        return []

    modules_elem = next((ch for ch in pom_root if _tag_matches(ch.tag, "modules")), None)
    if modules_elem is None:
        return []

    modules: list[str] = []
    for child in modules_elem:
        if not _tag_matches(child.tag, "module"):
            continue
        if not child.text:
            continue
        module_path = child.text.strip()
        if module_path:
            modules.append(module_path)

    return modules


def find_matching_maven_module_build_configs(repo_root: Path, artifact_id: str) -> list[Path]:
    """Find module ``pom.xml`` files likely associated with the artifact id.

    Parameters
    ----------
    repo_root : Path
        Root directory of the Maven repository.
    artifact_id : str
        Expected artifact id.

    Returns
    -------
    list[Path]
        Candidate module POM paths associated with the artifact id.
    """

    def _collect_from_parent_poms(parent_poms: list[Path]) -> list[Path]:
        candidates: list[Path] = []
        seen: set[Path] = set()

        for parent_pom in parent_poms:
            # Only aggregator poms with <modules> contribute module-path mapping.
            for module in extract_included_pom_modules(parent_pom):
                module_path = module.strip()
                if not module_path:
                    continue

                module_name = Path(module_path).name
                if artifact_id != module_name and not artifact_id.endswith(f"-{module_name}"):
                    continue

                module_pom = parent_pom.parent.joinpath(module_path, "pom.xml")
                if module_pom.is_file() and module_pom not in seen:
                    seen.add(module_pom)
                    candidates.append(module_pom)

        return candidates

    # Most Maven multi-module repos define modules in the repository-root pom.xml.
    # Check it first as a fast path.
    root_pom = repo_root.joinpath("pom.xml")
    if root_pom.is_file():
        root_candidates = _collect_from_parent_poms([root_pom])
        if root_candidates:
            return root_candidates

    # Some repositories have nested/independent reactor roots.
    # If root lookup does not match, broaden the search.
    nested_parent_poms = sorted(
        (pom for pom in repo_root.glob("**/pom.xml") if pom != root_pom),
        key=str,
    )
    return _collect_from_parent_poms(nested_parent_poms)


def find_nearest_modules_pom(
    pom_path: Path,
    repo_root: str | Path,
    *,
    max_depth: int = 50,
) -> str | None:
    """Find the nearest POM (self or Maven parent chain) that defines modules.

    Starting from ``pom_path``, this function checks whether the current POM is
    an aggregator (i.e., contains a non-empty ``<modules>`` section). If not, it
    resolves the Maven parent POM and repeats recursively until:

    * a POM with modules is found (returned), or
    * there is no parent POM resolvable within ``repo_root`` (returns ``None``),
      or
    * a cycle is detected (returns ``None``), or
    * ``max_depth`` is exceeded (returns ``None``).

    Parameters
    ----------
    pom_path : Path
        Path to the starting (child) ``pom.xml``.
    repo_root : str or pathlib.Path
        Repository root path used to validate parent POMs are inside the repo and
        to produce a repo-relative return value.
    max_depth : int, optional
        Maximum number of parent hops to attempt before aborting. Default is 50.

    Returns
    -------
    str | None
        Repo-relative path to the nearest POM that contains a non-empty
        ``<modules>`` section. If none is found, returns ``None``.
    """
    repo_root = Path(repo_root).resolve()
    current = pom_path.resolve()

    visited: set[Path] = set()
    depth = 0

    while True:
        if current in visited:
            return None
        visited.add(current)

        if pom_has_modules(current):
            try:
                return str(current.relative_to(repo_root))
            except ValueError:
                return None

        if depth >= max_depth:
            return None
        depth += 1

        parent_rel = detect_parent_pom(current, repo_root)
        if not parent_rel:
            return None

        parent_abs = Path(repo_root, parent_rel).resolve()
        if not parent_abs.is_file():
            return None

        current = parent_abs
