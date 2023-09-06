# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains helper functions to process CycloneDX SBOM."""

import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path

from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.dependency_analyzer.dependency_resolver import DependencyAnalyzer, DependencyInfo
from macaron.errors import MacaronError
from macaron.output_reporter.scm import SCMStatus
from macaron.repo_finder.repo_finder import find_valid_url

logger: logging.Logger = logging.getLogger(__name__)


class CycloneDXParserError(MacaronError):
    """The CycloneDX error class."""


def deserialize_bom_json(file_path: Path) -> dict:
    """Deserialize the bom.json file.

    Parameters
    ----------
    file_path : str
        Path to the bom.json file.

    Returns
    -------
    dict
        The BOM content as a dictionary.

    Raises
    ------
    CycloneDXParserError
        If the bom.json file cannot be located or deserialized.

    """
    # TODO: use the official CycloneDX library to validate and deserialize BOM files
    # once merged: https://github.com/CycloneDX/cyclonedx-python-lib/pull/290
    if not os.path.exists(file_path):
        raise CycloneDXParserError(f"Unable to locate the BOM file: {str(file_path)}.")

    with open(file_path, encoding="utf8") as file:
        try:
            return dict(json.load(file))
        except (ValueError, json.JSONDecodeError) as error:
            raise CycloneDXParserError(f"Could not process the dependencies at {file_path}: {error}") from None


def get_root_component(root_bom_path: Path) -> dict | None:
    """Get the root dependency component.

    Parameters
    ----------
    root_bom_path : str
        Path to the root bom.json file.

    Returns
    -------
    dict | None
        The root component.
    """
    try:
        root_bom = deserialize_bom_json(root_bom_path)
    except CycloneDXParserError as error:
        logger.error(error)
        return None
    try:
        return root_bom.get("metadata").get("component")  # type: ignore
    except AttributeError as error:
        logger.error(error)

    return None


def get_dep_components(
    root_bom_path: Path, child_bom_paths: list[Path] | None = None, recursive: bool = False
) -> Iterable[dict]:
    """Get dependency components.

    Parameters
    ----------
    root_bom_path : str
        Path to the root bom.json file.
    child_bom_paths: list[Path] | None
        The list of paths to sub-project bom.json files.
    recursive: bool
        Set to False to get the direct dependencies only (default).

    Yields
    ------
    dict
        The dependencies as CycloneDX components.
    """
    bom_objects: list[dict] = []
    try:
        root_bom = deserialize_bom_json(root_bom_path)
    except CycloneDXParserError as error:
        logger.error(error)
        return
    try:
        components = root_bom.get("components")
        bom_objects.append(root_bom)
    except AttributeError as error:
        logger.error(error)
        return

    if components is None:
        logger.error("The BOM file at %s misses components.", str(root_bom_path))
        return

    dependencies: list[str] = []
    modules: set[str] = set()  # Stores all module dependencies.
    for child_path in child_bom_paths or []:
        try:
            bom_objects.append(deserialize_bom_json(child_path))
        except CycloneDXParserError as error:
            logger.error(error)
            continue
    for bom in bom_objects:
        try:
            bom_ref = bom.get("metadata").get("component").get("bom-ref")  # type: ignore
            if bom_ref:
                modules.add(bom_ref)
            for node in bom.get("dependencies"):  # type: ignore
                if node.get("ref") == bom_ref or recursive:
                    dependencies.extend(node.get("dependsOn"))
        except AttributeError as error:
            logger.debug(error)

    for dependency in dependencies:
        if dependency in modules:
            continue
        for component in components:
            try:
                if dependency == component.get("bom-ref"):
                    yield component
            except AttributeError as error:
                logger.debug(error)


def convert_components_to_artifacts(
    components: Iterable[dict], root_component: dict | None = None
) -> dict[str, DependencyInfo]:
    """Convert CycloneDX components using internal artifact representation.

    Parameters
    ----------
    components : list[dict]
        The dependency components.
    root_component: dict | None
        The root CycloneDX component.

    Returns
    -------
    dict
        A dictionary where dependency artifacts are grouped based on "groupId:artifactId".
    """
    all_versions: dict[str, list[DependencyInfo]] = {}  # Stores all the versions of dependencies for debugging.
    latest_deps: dict[str, DependencyInfo] = {}  # Stores the latest version of dependencies.
    url_to_artifact: dict[str, set] = {}  # Used to detect artifacts that have similar repos.
    for component in components:
        try:
            # TODO make this function language agnostic when CycloneDX SBOM processing also is.
            # See https://github.com/oracle/macaron/issues/464
            key = f"{component.get('group')}:{component.get('name')}"
            if component.get("purl"):
                purl = PackageURL.from_string(str(component.get("purl")))
            else:
                # TODO remove maven assumption when optional non-existence of the component's purl is handled
                # See https://github.com/oracle/macaron/issues/464
                purl_string = f"pkg:maven/{component.get('group')}/{component.get('name')}"
                if component.get("version"):
                    purl_string = f"{purl_string}@{component.get('version')}"
                purl = PackageURL.from_string(purl_string)

            # According to PEP-0589 all keys must be present in a TypedDict.
            # See https://peps.python.org/pep-0589/#totality
            item = DependencyInfo(
                purl=purl,
                url="",
                note="",
                available=SCMStatus.AVAILABLE,
            )
            # Some of the components might miss external references.
            if component.get("externalReferences") is None:
                # In Java, development artifacts contain "SNAPSHOT" in the version.
                # If the SBOM generation completes with no build errors for submodules
                # the submodule would not be added as a dependency and we shouldn't reach here.
                # IN case of a build error, we use this as a heuristic to avoid analyzing
                # submodules that produce development artifacts in the same repo.
                if (
                    "snapshot" in (purl.version or "").lower()
                    # or "" is not necessary but mypy produces a FP otherwise.
                    and root_component
                    and purl.namespace == root_component.get("group")
                ):
                    continue
                logger.debug(
                    "Could not find external references for %s. Skipping...",
                    component.get("bom-ref"),
                )
            else:
                # Find a valid URL.
                item["url"] = find_valid_url(
                    link.get("url") for link in component.get("externalReferences")  # type: ignore
                )

            DependencyAnalyzer.add_latest_version(
                item=item, key=key, all_versions=all_versions, latest_deps=latest_deps, url_to_artifact=url_to_artifact
            )
        except (KeyError, AttributeError) as error:
            logger.debug(error)

    try:
        with open(os.path.join(global_config.output_path, "sbom_debug.json"), "w", encoding="utf8") as debug_file:
            debug_file.write(json.dumps(all_versions, indent=4))
    except OSError as error:
        logger.error(error)

    return latest_deps


def get_deps_from_sbom(sbom_path: str | Path) -> dict[str, DependencyInfo]:
    """Get the dependencies from a provided SBOM.

    Parameters
    ----------
    sbom_path : str | Path
        The path to the SBOM file.

    Returns
    -------
        A dictionary where dependency artifacts are grouped based on "groupId:artifactId".
    """
    return convert_components_to_artifacts(
        get_dep_components(
            root_bom_path=Path(sbom_path),
            recursive=defaults.getboolean(
                "dependency.resolver",
                "recursive",
                fallback=False,
            ),
        )
    )
