# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic for finding repositories of PyPI projects."""
import logging

from packageurl import PackageURL

from macaron.repo_finder.repo_finder_enums import RepoFinderInfo
from macaron.repo_finder.repo_validator import find_valid_repository_url
from macaron.slsa_analyzer.package_registry import PACKAGE_REGISTRIES, PyPIRegistry
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIPackageJsonAsset, find_or_create_pypi_asset
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
    pypi_info = None
    if package_registries_info:
        # Find the package registry info object that contains the PyPI registry and has the pypi build tool.
        pypi_info = next(
            (
                info
                for info in package_registries_info
                if isinstance(info.package_registry, PyPIRegistry) and info.build_tool_name in {"poetry", "pip"}
            ),
            None,
        )
        if not pypi_info:
            return "", RepoFinderInfo.PYPI_NO_REGISTRY

    if not purl.version:
        return "", RepoFinderInfo.NO_VERSION_PROVIDED

    # Create the asset.
    if pypi_info:
        pypi_asset = find_or_create_pypi_asset(purl.name, purl.version, pypi_info)
    else:
        # If this function has been reached via find-source, we do not store the asset.
        pypi_registry = next((registry for registry in PACKAGE_REGISTRIES if isinstance(registry, PyPIRegistry)), None)
        if not pypi_registry:
            return "", RepoFinderInfo.PYPI_NO_REGISTRY
        pypi_asset = PyPIPackageJsonAsset(purl.name, purl.version, False, pypi_registry, {}, "")

    if not pypi_asset:
        # This should be unreachable, as the pypi_registry has already been confirmed to be of type PyPIRegistry.
        return "", RepoFinderInfo.PYPI_NO_REGISTRY

    if not pypi_asset.package_json and not pypi_asset.download(dest=""):
        return "", RepoFinderInfo.PYPI_HTTP_ERROR

    url_dict = pypi_asset.get_project_links()
    if not url_dict:
        return "", RepoFinderInfo.PYPI_JSON_ERROR

    # Look for the repository URL.
    fixed_url = find_valid_repository_url(url_dict.values())
    if not fixed_url:
        return "", RepoFinderInfo.PYPI_NO_URLS

    logger.debug("Found repository URL from PyPI: %s", fixed_url)
    pypi_asset.has_repository = True
    return fixed_url, RepoFinderInfo.FOUND_FROM_PYPI
