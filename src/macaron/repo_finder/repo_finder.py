# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module contains the logic for using/calling the different repo finders.

Input
-----
The entry point of the repo finder depends on the type of PURL being analyzed.
- If passing a PURL representing an artifact, the ``find_repo`` function in this file should be called.
- If passing a PURL representing a repository, the ``to_repo_path`` function in this file should be called.

Artifact PURLs
--------------
For artifact PURLs, the PURL type determines how the repositories are searched for.
Currently, for Maven PURLs, SCM meta data is retrieved from the matching POM retrieved from Maven Central (or
other configured location).

For Python, .NET, Rust, and NodeJS type PURLs, Google's Open Source Insights API is used to find the meta data.

In either case, any repository links are extracted from the meta data, then checked for validity via
``repo_validator::find_valid_repository_url`` which accepts URLs that point to a GitHub repository or similar.

Repository PURLs
----------------
For repository PURLs, the type is checked against the configured valid domains, and accepted or rejected based
on that data.

Result
------
If all goes well, a repository URL that matches the initial artifact or repository PURL will be returned for
analysis.
"""

import logging
import os
from urllib.parse import ParseResult, urlunparse

from git import InvalidGitRepositoryError
from packageurl import PackageURL
from pydriller import Git

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.errors import CloneError, RepoCheckOutError
from macaron.repo_finder import repo_finder_pypi, to_domain_from_known_purl_types
from macaron.repo_finder.commit_finder import find_commit, match_tags
from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_finder_deps_dev import DepsDevRepoFinder
from macaron.repo_finder.repo_finder_enums import CommitFinderInfo, RepoFinderInfo
from macaron.repo_finder.repo_finder_java import JavaRepoFinder
from macaron.repo_finder.repo_utils import (
    check_repo_urls_are_equivalent,
    generate_report,
    get_git_service,
    get_local_repos_path,
)
from macaron.slsa_analyzer.git_url import (
    GIT_REPOS_DIR,
    check_out_repo_target,
    get_remote_origin_of_local_repo,
    get_remote_vcs_url,
    get_repo_dir_name,
    get_tags_via_git_remote,
    is_empty_repo,
    is_remote_repo,
    resolve_local_path,
)
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


def find_repo(
    purl: PackageURL,
    check_latest_version: bool = True,
    package_registries_info: list[PackageRegistryInfo] | None = None,
) -> tuple[str, RepoFinderInfo]:
    """Retrieve the repository URL that matches the given PURL.

    Parameters
    ----------
    purl : PackageURL
        The parsed PURL to convert to the repository path.
    check_latest_version: bool
        A flag that determines whether the latest version of the PURL is also checked.
    package_registries_info: list[PackageRegistryInfo] | None
        The list of package registry information if available.
        If no package registries are loaded, this can be set to None.

    Returns
    -------
    tuple[str, RepoFinderOutcome] :
        The repository URL for the passed package, if found, and the outcome to report.
    """
    repo_finder: BaseRepoFinder
    if purl.type == "maven":
        repo_finder = JavaRepoFinder()
    elif defaults.getboolean("repofinder", "use_open_source_insights") and purl.type in {
        "pypi",
        "nuget",
        "cargo",
        "npm",
    }:
        repo_finder = DepsDevRepoFinder()
    else:
        logger.debug("No Repo Finder found for package type: %s of %s", purl.type, purl)
        return "", RepoFinderInfo.UNSUPPORTED_PACKAGE_TYPE

    # Call Repo Finder and return first valid URL
    logger.debug("Analyzing %s with Repo Finder: %s", purl, type(repo_finder))
    found_repo, outcome = repo_finder.find_repo(purl)

    if not found_repo:
        found_repo, outcome = find_repo_alternative(purl, outcome, package_registries_info)

    if check_latest_version and not defaults.getboolean("repofinder", "try_latest_purl", fallback=True):
        check_latest_version = False

    if found_repo or not check_latest_version:
        return found_repo, outcome

    # Try to find the latest version repo.
    logger.debug("Could not find repo for PURL: %s", purl)
    latest_version_purl = get_latest_purl_if_different(purl)
    if not latest_version_purl:
        logger.debug("Could not find newer PURL than provided: %s", purl)
        return "", RepoFinderInfo.NO_NEWER_VERSION

    found_repo, outcome = DepsDevRepoFinder().find_repo(latest_version_purl)
    if found_repo:
        return found_repo, outcome

    if not found_repo:
        found_repo, outcome = find_repo_alternative(latest_version_purl, outcome, package_registries_info)

    if not found_repo:
        logger.debug("Could not find repo from latest version of PURL: %s", latest_version_purl)
        return "", RepoFinderInfo.LATEST_VERSION_INVALID

    return found_repo, outcome


def find_repo_alternative(
    purl: PackageURL, outcome: RepoFinderInfo, package_registries_info: list[PackageRegistryInfo] | None = None
) -> tuple[str, RepoFinderInfo]:
    """Use PURL type specific methods to find the repository when the standard methods have failed.

    Parameters
    ----------
    purl : PackageURL
        The parsed PURL to convert to the repository path.
    outcome: RepoFinderInfo
        A previous outcome to report if this method does nothing.
    package_registries_info: list[PackageRegistryInfo] | None
        The list of package registry information if available.
        If no package registries are loaded, this can be set to None.

    Returns
    -------
    tuple[str, RepoFinderOutcome] :
        The repository URL for the passed package, if found, and the outcome to report.
    """
    found_repo = ""
    if purl.type == "pypi":
        found_repo, outcome = repo_finder_pypi.find_repo(purl, package_registries_info)

    if not found_repo:
        logger.debug(
            "Could not find repository using type specific (%s) methods for PURL %s. Outcome: %s",
            purl.type,
            purl,
            outcome,
        )

    return found_repo, outcome


def to_repo_path(purl: PackageURL, available_domains: list[str]) -> str | None:
    """Return the repository path from the PURL string.

    This method only supports converting a PURL with the following format:

        pkg:<type>/<namespace>/<name>[...]

    Where ``type`` could be either:
    - The pre-defined repository-based PURL type as defined in
    https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst

    - The supported git service domains (e.g. ``github.com``) defined in ``available_domains``.

    The repository path will be generated with the following format ``https://<type>/<namespace>/<name>``.

    Parameters
    ----------
    purl : PackageURL
        The parsed PURL to convert to the repository path.
    available_domains: list[str]
        The list of available domains

    Returns
    -------
    str | None
        The URL to the repository which the PURL is referring to or None if we cannot convert it.
    """
    domain = to_domain_from_known_purl_types(purl.type) or (purl.type if purl.type in available_domains else None)
    if not domain:
        logger.info("The PURL type of %s is not valid as a repository type.", purl)
        return None

    if not purl.namespace:
        logger.error("Expecting a non-empty namespace from %s.", purl)
        return None

    # If the PURL contains a commit digest or version tag, they will be used after the repository has been resolved.
    return urlunparse(
        ParseResult(
            scheme="https",
            netloc=domain,
            path=os.path.join(purl.namespace, purl.name),
            params="",
            query="",
            fragment="",
        )
    )


def find_source(purl_string: str, input_repo: str | None, latest_version_fallback: bool = True) -> bool:
    """Perform repo and commit finding for a passed PURL, or commit finding for a passed PURL and repo.

    Parameters
    ----------
    purl_string: str
        The PURL string of the target.
    input_repo: str | None
        The repository path optionally provided by the user.
    latest_version_fallback: bool
        A flag that determines whether the latest version of the same artifact can be checked as a fallback option.

    Returns
    -------
    bool
        True if the source was found.
    """
    try:
        purl: PackageURL | None = PackageURL.from_string(purl_string)
    except ValueError as error:
        logger.error("Could not parse PURL: '%s'. Error: %s", purl_string, error)
        return False

    if not purl:
        # Unreachable.
        return False

    checked_latest_purl = False
    if not purl.version:
        purl = get_latest_purl_if_different(purl)
        if not purl or not purl.version:
            logger.error("PURL is missing version.")
            return False
        checked_latest_purl = True

    found_repo = input_repo
    if not found_repo:
        logger.debug("Searching for repo of PURL: %s", purl)
        found_repo, _ = find_repo(purl)

    if not found_repo:
        logger.error("Could not find repo for PURL: %s", purl)
        return False

    # Disable other loggers for cleaner output.
    logging.getLogger("macaron.slsa_analyzer.analyzer").disabled = True

    digest = ""
    if defaults.getboolean("repofinder", "find_source_should_clone"):
        # Clone the repo to retrieve the tags.
        logger.debug("Preparing repo: %s", found_repo)
        repo_dir = os.path.join(global_config.output_path, GIT_REPOS_DIR)
        logging.getLogger("macaron.slsa_analyzer.git_url").disabled = True
        # The prepare_repo function will also check the latest version of the artifact if required.
        git_obj, _ = prepare_repo(repo_dir, found_repo, purl=purl, latest_version_fallback=not checked_latest_purl)

        if git_obj:
            digest = git_obj.get_head().hash

        if not digest:
            return False
    else:
        # Retrieve the tags using a remote git operation.
        tags = get_tags_via_git_remote(found_repo)
        if not tags:
            return False

        matches, _ = match_tags(list(tags.keys()), purl.name, purl.version)

        if not matches:
            return False

        matched_tag = matches[0]
        digest = tags[matched_tag]

        if not digest:
            logger.error("Could not find commit for purl / repository: %s / %s", purl, found_repo)
            if not latest_version_fallback or checked_latest_purl:
                return False

            # When not cloning the latest version must be checked here.
            latest_version_purl = get_latest_purl_if_different(purl)
            if not latest_version_purl:
                return False

            latest_repo = get_latest_repo_if_different(latest_version_purl, found_repo)
            if not latest_repo:
                return False

            return find_source(str(purl), latest_repo, False)

    if not input_repo:
        logger.info("Found repository for PURL: %s", found_repo)

    logger.info("Found commit for PURL: %s", digest)

    if not generate_report(purl_string, digest, found_repo, os.path.join(global_config.output_path, "reports")):
        return False

    return True


def get_latest_purl_if_different(purl: PackageURL) -> PackageURL | None:
    """Return the latest version of an artifact represented by a PURL, if it is different.

    Parameters
    ----------
    purl : PackageURL | None
        The PURL of the analysis target.

    Returns
    -------
    PackageURL | None
        The latest PURL, or None if they are the same or an error occurs.
    """
    if purl.version:
        namespace = purl.namespace + "/" if purl.namespace else ""
        no_version_purl = PackageURL.from_string(f"pkg:{purl.type}/{namespace}{purl.name}")
    else:
        no_version_purl = purl

    latest_version_purl, _ = DepsDevRepoFinder.get_latest_version(no_version_purl)
    if not latest_version_purl:
        logger.error("Latest version PURL could not be found.")
        return None

    if latest_version_purl == purl:
        logger.error("Latest version PURL is the same as the current.")
        return None

    logger.debug("Found new version of PURL: %s", latest_version_purl)
    return latest_version_purl


def get_latest_repo_if_different(latest_version_purl: PackageURL, original_repo: str) -> str:
    """Return the repository of the passed PURL if it is different to the passed repository.

    Parameters
    ----------
    latest_version_purl: PackageURL
        The PURL to use.
    original_repo: str
        The repository to compare against.

    Returns
    -------
    str
        The latest repository, or an empty string if not found.
    """
    latest_repo, _ = find_repo(latest_version_purl, False)
    if not latest_repo:
        logger.error("Could not find repository from latest PURL: %s", latest_version_purl)
        return ""

    if check_repo_urls_are_equivalent(original_repo, latest_repo):
        logger.error(
            "Repository from latest PURL is equivalent to original repository: %s ~= %s", latest_repo, original_repo
        )
        return ""

    logger.debug("Found new repository from latest PURL: %s", latest_repo)
    return latest_repo


def prepare_repo(
    target_dir: str,
    repo_path: str,
    branch_name: str = "",
    digest: str = "",
    purl: PackageURL | None = None,
    latest_version_fallback: bool = True,
) -> tuple[Git | None, CommitFinderInfo]:
    """Prepare the target repository for analysis.

    If ``repo_path`` is a remote path, the target repo is cloned to ``{target_dir}/{unique_path}``.
    The ``unique_path`` of a repository will depend on its remote url.
    For example, if given the ``repo_path`` https://github.com/org/name.git, it will
    be cloned to ``{target_dir}/github_com/org/name``.

    If ``repo_path`` is a local path, this method will check if ``repo_path`` resolves to a directory inside
    ``local_repos_path`` and to a valid git repository.

    Parameters
    ----------
    target_dir : str
        The directory where all remote repository will be cloned.
    repo_path : str
        The path to the repository, can be either local or remote.
    branch_name : str
        The name of the branch we want to checkout.
    digest : str
        The hash of the commit that we want to checkout in the branch.
    purl : PackageURL | None
        The PURL of the analysis target.
    latest_version_fallback: bool
        A flag that determines whether the latest version of the same artifact can be checked as a fallback option.

    Returns
    -------
    tuple[Git | None, CommitFinderInfo]
            The pydriller.Git object of the repository or None if error, and the outcome of the Commit Finder.
    """
    # TODO: separate the logic for handling remote and local repos instead of putting them into this method.
    logger.info(
        "Preparing the repository for the analysis (path=%s, branch=%s, digest=%s)",
        repo_path,
        branch_name,
        digest,
    )

    is_remote = is_remote_repo(repo_path)
    commit_finder_outcome = CommitFinderInfo.NOT_USED

    if is_remote:
        logger.info("The path to repo %s is a remote path.", repo_path)
        resolved_remote_path = get_remote_vcs_url(repo_path)
        if not resolved_remote_path:
            logger.error("The provided path to repo %s is not a valid remote path.", repo_path)
            return None, commit_finder_outcome

        git_service = get_git_service(resolved_remote_path)
        repo_unique_path = get_repo_dir_name(resolved_remote_path)
        resolved_local_path = os.path.join(target_dir, repo_unique_path)
        logger.info("Cloning the repository.")
        try:
            git_service.clone_repo(resolved_local_path, resolved_remote_path)
        except CloneError as error:
            logger.error("Cannot clone %s: %s", resolved_remote_path, str(error))
            return None, commit_finder_outcome
    else:
        logger.info("Checking if the path to repo %s is a local path.", repo_path)
        resolved_local_path = resolve_local_path(get_local_repos_path(), repo_path)

    if resolved_local_path:
        try:
            git_obj = Git(resolved_local_path)
        except InvalidGitRepositoryError:
            logger.error("No git repo exists at %s.", resolved_local_path)
            return None, commit_finder_outcome
    else:
        logger.error("Error happened while preparing the repo.")
        return None, commit_finder_outcome

    if is_empty_repo(git_obj):
        logger.error("The target repository does not have any commit.")
        return None, commit_finder_outcome

    # Find the digest if a version has been specified.
    if not digest and purl and purl.version:
        found_digest, commit_finder_outcome = find_commit(git_obj, purl)
        if not found_digest:
            logger.error("Could not map the input purl string to a specific commit in the corresponding repository.")
            if not latest_version_fallback:
                return None, commit_finder_outcome
            # If the commit could not be found, check if the latest version of the artifact has a different repository.
            latest_purl = get_latest_purl_if_different(purl)
            if not latest_purl:
                return None, commit_finder_outcome
            latest_repo = get_latest_repo_if_different(latest_purl, repo_path)
            if not latest_repo:
                return None, commit_finder_outcome
            return prepare_repo(latest_repo, latest_repo, target_dir, latest_version_fallback=False)

        digest = found_digest

    # Checking out the specific branch or commit. This operation varies depends on the git service that the
    # repository uses.
    if not is_remote:
        # If the repo path provided by the user is a local path, we need to get the actual origin remote URL of
        # the repo to decide on the suitable git service.
        origin_remote_url = get_remote_origin_of_local_repo(git_obj)
        if is_remote_repo(origin_remote_url):
            # The local repo's origin remote url is a remote URL (e.g https://host.com/a/b): In this case, we obtain
            # the corresponding git service using ``self.get_git_service``.
            git_service = get_git_service(origin_remote_url)
        else:
            # The local repo's origin remote url is a local path (e.g /path/to/local/...). This happens when the
            # target repository is a clone from another local repo or is a clone from a git archive -
            # https://git-scm.com/docs/git-archive: In this case, we fall-back to the generic function
            # ``git_url.check_out_repo_target``.
            if not check_out_repo_target(git_obj, branch_name, digest, not is_remote):
                logger.error("Cannot checkout the specific branch or commit of the target repo.")
                return None, commit_finder_outcome

            return git_obj, commit_finder_outcome

    try:
        git_service.check_out_repo(git_obj, branch_name, digest, not is_remote)
    except RepoCheckOutError as error:
        logger.error("Failed to check out repository at %s", resolved_local_path)
        logger.error(error)
        return None, commit_finder_outcome

    return git_obj, commit_finder_outcome
