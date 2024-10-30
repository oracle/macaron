# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the utility functions for repo and commit finder operations."""
import json
import logging
import os
import string

from git import InvalidGitRepositoryError
from packageurl import PackageURL
from pydriller import Git

from macaron.config.global_config import global_config
from macaron.errors import CloneError, RepoCheckOutError
from macaron.repo_finder.commit_finder import find_commit
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


def create_report(purl: str, commit: str, repo: str) -> str:
    """Create and return the JSON report containing the input and output information.

    Parameters
    ----------
    purl: str
        The PackageURL of the target artifact, as a string.
    commit: str
        The commit hash to report.
    repo: str
        The repository to report.

    Returns
    -------
    str
        The JSON report as a string.
    """
    data = {"purl": purl, "commit": commit, "repo": repo}
    if "github.com" in repo:
        data["url"] = f"{repo}/commit/{commit}"
    return json.dumps(data, indent=4)


def create_filename(purl: PackageURL) -> str:
    """Create the filename of the report based on the PURL.

    Parameters
    ----------
    purl: PackageURL
        The PackageURL of the artifact.

    Returns
    -------
    str
        The filename to save the report under.
    """

    def convert_to_path(text: str) -> str:
        """Convert a PackageURL component to a path safe form."""
        allowed_chars = string.ascii_letters + string.digits + "-"
        return "".join(c if c in allowed_chars else "_" for c in text)

    filename = f"{convert_to_path(purl.type)}"
    if purl.namespace:
        filename = filename + f"/{convert_to_path(purl.namespace)}"
    filename = filename + f"/{convert_to_path(purl.name)}/{convert_to_path(purl.name)}.source.json"
    return filename


def generate_report(purl: str, commit: str, repo: str, target_dir: str) -> bool:
    """Create the report and save it to the passed directory.

    Parameters
    ----------
    purl: str
        The PackageURL of the target artifact, as a string.
    commit: str
        The commit hash to report.
    repo: str
        The repository to report.
    target_dir: str
        The path of the directory where the report will be saved.

    Returns
    -------
    bool
        True if the report was created. False otherwise.
    """
    report_json = create_report(purl, commit, repo)

    try:
        purl_object = PackageURL.from_string(purl)
    except ValueError as error:
        logger.debug("Failed to parse purl string as PURL: %s", error)
        return False

    filename = create_filename(purl_object)
    fullpath = f"{target_dir}/{filename}"

    os.makedirs(os.path.dirname(fullpath), exist_ok=True)
    logger.info("Writing report to: %s", fullpath)

    try:
        with open(fullpath, "w", encoding="utf-8") as file:
            file.write(report_json)
    except OSError as error:
        logger.debug("Failed to write report to file: %s", error)
        return False

    logger.info("Report written to: %s", fullpath)

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
