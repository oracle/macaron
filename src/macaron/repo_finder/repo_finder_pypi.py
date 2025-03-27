# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic for finding repositories of PyPI projects."""
import logging

from packageurl import PackageURL

from macaron.repo_finder.repo_finder_enums import RepoFinderInfo
from macaron.repo_finder.repo_validator import find_valid_repository_url
from macaron.slsa_analyzer.package_registry import PyPIRegistry
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIPackageJsonAsset
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


def find_repo(
    purl: PackageURL, package_registries_info: list[PackageRegistryInfo] | None = None
) -> tuple[str, RepoFinderInfo]:
    """Retrieve the repository URL that matches the given PyPI PURL.

    Parameters
    ----------
    purl : PackageURL
        The parsed PURL to convert to the repository path.
    package_registries_info: list[PackageRegistryInfo] | None
        The list of package registry information if available.
        If no package registries are loaded, this can be set to None.

    Returns
    -------
    tuple[str, RepoFinderOutcome] :
        The repository URL for the passed package, if found, and the outcome to report.
    """
    if not package_registries_info:
        logger.debug("No package registries are loaded.")
        return "", RepoFinderInfo.PYPI_NO_REGISTRY

    # Find the package registry info object that contains the PyPI registry and has the pypi build tool.
    pypi_info = next(
        (
            info
            for info in package_registries_info
            if isinstance(info.package_registry, PyPIRegistry) and info.build_tool_name == "pypi"
        ),
        None,
    )

    if not pypi_info or not isinstance(pypi_info.package_registry, PyPIRegistry):
        logger.debug("PyPI package registry not available.")
        return "", RepoFinderInfo.PYPI_NO_REGISTRY

    pypi_asset = None
    from_metadata = False
    for existing_asset in pypi_info.metadata:
        if not isinstance(existing_asset, PyPIPackageJsonAsset):
            continue

        if existing_asset.component_name == purl.name and existing_asset.component_version == purl.version:
            pypi_asset = existing_asset
            from_metadata = True
            break

    if not pypi_asset:
        pypi_registry = pypi_info.package_registry
        pypi_asset = PyPIPackageJsonAsset(purl.name, purl.version, False, pypi_registry, {})

    if not pypi_asset.package_json and not pypi_asset.download(dest=""):
        return "", RepoFinderInfo.PYPI_HTTP_ERROR

    if not from_metadata:
        # Save the asset for later use.
        pypi_info.metadata.append(pypi_asset)

    url_dict = pypi_asset.get_project_links()
    if not url_dict:
        return "", RepoFinderInfo.PYPI_JSON_ERROR

    # Look for the repository URL.
    fixed_url = find_valid_repository_url(url_dict.values(), ["github.com"])
    if not fixed_url:
        return "", RepoFinderInfo.PYPI_NO_URLS

    logger.debug("Found repository URL from PyPI: %s", fixed_url)
    pypi_asset.has_repository = True
    return fixed_url, RepoFinderInfo.FOUND_FROM_PYPI
