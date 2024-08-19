# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
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
from macaron.repo_finder import to_domain_from_known_purl_types
from macaron.repo_finder.commit_finder import find_commit
from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_finder_deps_dev import DepsDevRepoFinder
from macaron.repo_finder.repo_finder_java import JavaRepoFinder
from macaron.slsa_analyzer.git_service import GIT_SERVICES, BaseGitService
from macaron.slsa_analyzer.git_service.base_git_service import NoneGitService
from macaron.slsa_analyzer.git_url import (
    GIT_REPOS_DIR,
    check_out_repo_target,
    get_remote_origin_of_local_repo,
    get_remote_vcs_url,
    get_repo_dir_name,
    is_empty_repo,
    is_remote_repo,
    resolve_local_path,
)

logger: logging.Logger = logging.getLogger(__name__)


def find_repo(purl: PackageURL) -> str:
    """Retrieve the repository URL that matches the given PURL.

    Parameters
    ----------
    purl : PackageURL
        The parsed PURL to convert to the repository path.

    Returns
    -------
    str :
        The repository URL found for the passed package.
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
        return ""

    # Call Repo Finder and return first valid URL
    logger.debug("Analyzing %s with Repo Finder: %s", purl, type(repo_finder))
    return repo_finder.find_repo(purl)


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
        logger.info("The PURL type of %s is not valid as a repository type. Trying to find the repository...", purl)
        # Try to find the repository
        return find_repo(purl)

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


def find_source(purl_string: str, repo: str | None) -> bool:
    """Perform repo and commit finding for a passed PURL, or commit finding for a passed PURL and repo.

    Parameters
    ----------
    purl_string: str
        The PURL string of the target.
    repo: str | None
        The optional repository path.

    Returns
    -------
    bool
        True if the source was found.
    """
    try:
        purl = PackageURL.from_string(purl_string)
    except ValueError as error:
        logger.error("Could not parse PURL: %s", error)
        return False

    found_repo = repo
    if not repo:
        logger.debug("Searching for repo of PURL: %s", purl)
        found_repo = find_repo(purl)

    if not found_repo:
        logger.error("Could not find repo for PURL: %s", purl)
        return False

    # Disable other loggers for cleaner output.
    analyzer_logger = logging.getLogger("macaron.slsa_analyzer.analyzer")
    analyzer_logger.disabled = True
    git_logger = logging.getLogger("macaron.slsa_analyzer.git_url")
    git_logger.disabled = True

    # Prepare the repo.
    logger.debug("Preparing repo: %s", found_repo)
    repo_dir = os.path.join(global_config.output_path, GIT_REPOS_DIR)
    git_obj = prepare_repo(
        repo_dir,
        found_repo,
        purl=purl,
    )

    if not git_obj:
        # TODO expand this message to cover cases where the obj was not created due to lack of correct tag.
        logger.error("Could not resolve repository: %s", found_repo)
        return False

    try:
        digest = git_obj.get_head().hash
    except ValueError:
        logger.debug("Could not retrieve commit hash from repository.")
        return False

    if not digest:
        logger.error("Could not find commit for purl / repository: %s / %s", purl, found_repo)
        return False

    if not repo:
        logger.info("Found repository for PURL: %s", found_repo)
    logger.info("Found commit for PURL: %s", digest)

    logger.info("%s/commit/%s", found_repo, digest)

    return True


def prepare_repo(
    target_dir: str,
    repo_path: str,
    branch_name: str = "",
    digest: str = "",
    purl: PackageURL | None = None,
) -> Git | None:
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

    Returns
    -------
    Git | None
        The pydriller.Git object of the repository or None if error.
    """
    # TODO: separate the logic for handling remote and local repos instead of putting them into this method.
    logger.info(
        "Preparing the repository for the analysis (path=%s, branch=%s, digest=%s)",
        repo_path,
        branch_name,
        digest,
    )

    resolved_local_path = ""
    is_remote = is_remote_repo(repo_path)

    if is_remote:
        logger.info("The path to repo %s is a remote path.", repo_path)
        resolved_remote_path = get_remote_vcs_url(repo_path)
        if not resolved_remote_path:
            logger.error("The provided path to repo %s is not a valid remote path.", repo_path)
            return None

        git_service = get_git_service(resolved_remote_path)
        repo_unique_path = get_repo_dir_name(resolved_remote_path)
        resolved_local_path = os.path.join(target_dir, repo_unique_path)
        logger.info("Cloning the repository.")
        try:
            git_service.clone_repo(resolved_local_path, resolved_remote_path)
        except CloneError as error:
            logger.error("Cannot clone %s: %s", resolved_remote_path, str(error))
            return None
    else:
        logger.info("Checking if the path to repo %s is a local path.", repo_path)
        resolved_local_path = resolve_local_path(get_local_repos_path(), repo_path)

    if resolved_local_path:
        try:
            git_obj = Git(resolved_local_path)
        except InvalidGitRepositoryError:
            logger.error("No git repo exists at %s.", resolved_local_path)
            return None
    else:
        logger.error("Error happened while preparing the repo.")
        return None

    if is_empty_repo(git_obj):
        logger.error("The target repository does not have any commit.")
        return None

    # Find the digest and branch if a version has been specified
    if not digest and purl and purl.version:
        found_digest = find_commit(git_obj, purl)
        if not found_digest:
            logger.error("Could not map the input purl string to a specific commit in the corresponding repository.")
            return None
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
                return None

            return git_obj

    try:
        git_service.check_out_repo(git_obj, branch_name, digest, not is_remote)
    except RepoCheckOutError as error:
        logger.error("Failed to check out repository at %s", resolved_local_path)
        logger.error(error)
        return None

    return git_obj


def get_local_repos_path() -> str:
    """Get the local repos path from global config or use default.

    If the directory does not exist, it is created.
    """
    local_repos_path = (
        global_config.local_repos_path
        if global_config.local_repos_path
        else os.path.join(global_config.output_path, GIT_REPOS_DIR, "local_repos")
    )
    if not os.path.exists(local_repos_path):
        os.makedirs(local_repos_path, exist_ok=True)
    return local_repos_path


def get_git_service(remote_path: str | None) -> BaseGitService:
    """Return the git service used from the remote path.

    Parameters
    ----------
    remote_path : str | None
        The remote path of the repo.

    Returns
    -------
    BaseGitService
        The git service derived from the remote path.
    """
    if remote_path:
        for git_service in GIT_SERVICES:
            if git_service.is_detected(remote_path):
                return git_service

    return NoneGitService()
