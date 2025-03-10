# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic for finding repositories of PyPI projects."""
import logging
import urllib.parse

from packageurl import PackageURL

from macaron.repo_finder.repo_finder_enums import RepoFinderInfo
from macaron.slsa_analyzer.package_registry import PACKAGE_REGISTRIES, PyPIRegistry
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIPackageJsonAsset
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


def find_repo(
    purl: PackageURL, all_package_registries: list[PackageRegistryInfo] | None = None
) -> tuple[str, RepoFinderInfo]:
    """Retrieve the repository URL that matches the given PyPI PURL.

    Parameters
    ----------
    purl : PackageURL
        The parsed PURL to convert to the repository path.
    all_package_registries: list[PackageRegistryInfo] | None
        The context of the current analysis, if any.

    Returns
    -------
    tuple[str, RepoFinderOutcome] :
        The repository URL for the passed package, if found, and the outcome to report.
    """
    pypi_registry = next((registry for registry in PACKAGE_REGISTRIES if isinstance(registry, PyPIRegistry)), None)
    if not pypi_registry:
        return "", RepoFinderInfo.PYPI_NO_REGISTRY

    pypi_registry.load_defaults()
    pypi_asset = PyPIPackageJsonAsset(purl.name, purl.version, False, pypi_registry, {})
    if not pypi_asset.download(dest=""):
        return "", RepoFinderInfo.PYPI_HTTP_ERROR

    if all_package_registries:
        # Find the package registry info object that contains the PyPI registry and has the pypi build tool.
        registry_info = next(
            (
                info
                for info in all_package_registries
                if info.package_registry == pypi_registry and info.build_tool_name == "pypi"
            ),
            None,
        )
        if registry_info:
            # Save the asset for later use.
            registry_info.metadata.append(pypi_asset)

    url_dict = pypi_asset.get_project_links()
    if not url_dict:
        return "", RepoFinderInfo.PYPI_JSON_ERROR

    for url_key in url_dict:
        url = url_dict[url_key]
        parsed_url = urllib.parse.urlparse(url)
        if not parsed_url.hostname:
            continue
        if not parsed_url.hostname.lower() == "github.com":
            continue
        # The path starts with a "/".
        split_path = parsed_url.path[1:].split("/")
        if not split_path or len(split_path) < 2:
            continue
        # Fix the URL so that it is the base GitHub URL. E.g. github.com/{owner}/{repo}
        fixed_url = urllib.parse.ParseResult(
            scheme=parsed_url.scheme,
            netloc=parsed_url.netloc,
            path=f"{split_path[0]}/{split_path[1]}",
            params=parsed_url.params,
            query=parsed_url.query,
            fragment=parsed_url.fragment,
        ).geturl()
        logger.debug("Found repository URL from PyPI: %s", fixed_url)
        pypi_asset.has_repository = True
        return fixed_url, RepoFinderInfo.FOUND_FROM_PYPI

    return "", RepoFinderInfo.PYPI_NO_URLS
