# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic for finding repositories of NPM projects."""
import logging

from packageurl import PackageURL

from macaron.repo_finder.repo_finder_enums import RepoFinderInfo
from macaron.repo_finder.repo_validator import find_valid_repository_url
from macaron.slsa_analyzer.package_registry import PACKAGE_REGISTRIES, NPMRegistry
from macaron.slsa_analyzer.package_registry.npm_registry import (
    NPMPackageJsonAsset,
    find_or_create_npm_asset,
)
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


def find_repo(
    purl: PackageURL, package_registries_info: list[PackageRegistryInfo] | None = None
) -> tuple[str, RepoFinderInfo]:
    """Retrieve the repository URL that matches the given NPM PURL.

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
    npm_info = None
    if package_registries_info:
        # Find the package registry info object that contains the NPM registry.
        npm_info = next(
            (info for info in package_registries_info if isinstance(info.package_registry, NPMRegistry)),
            None,
        )
        if not npm_info:
            return "", RepoFinderInfo.NPM_NO_REGISTRY

    if not purl.version:
        return "", RepoFinderInfo.NO_VERSION_PROVIDED

    # Create the asset.
    if npm_info:
        npm_asset = find_or_create_npm_asset(purl.name, purl.namespace, purl.version, npm_info)
    else:
        # If this function has been reached via find-source, we do not store the asset.
        npm_registry = next((registry for registry in PACKAGE_REGISTRIES if isinstance(registry, NPMRegistry)), None)
        if not npm_registry:
            return "", RepoFinderInfo.NPM_NO_REGISTRY
        npm_asset = NPMPackageJsonAsset(purl.name, purl.namespace, purl.version, npm_registry, {}, "", "", "", False)

    if not npm_asset:
        # This should be unreachable, as the npm_registry has already been confirmed to be of type NPMRegistry.
        return "", RepoFinderInfo.NPM_NO_REGISTRY

    if not npm_asset.package_json and not npm_asset.download(dest=""):
        return "", RepoFinderInfo.NPM_HTTP_ERROR

    url_dict = npm_asset.get_project_links()
    if not url_dict:
        return "", RepoFinderInfo.NPM_JSON_ERROR

    # Look for the repository URL.
    fixed_url = find_valid_repository_url(url_dict.values())
    if not fixed_url:
        return "", RepoFinderInfo.NPM_NO_URLS

    logger.debug("Found repository URL from NPM: %s", fixed_url)
    npm_asset.has_repository = True
    return fixed_url, RepoFinderInfo.FOUND_FROM_NPM
