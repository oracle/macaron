# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the utility functions for repo and commit finder operations."""
import json
import logging
import os
import string
from urllib.parse import urlparse

from packageurl import PackageURL

from macaron.config.global_config import global_config
from macaron.slsa_analyzer.git_service import GIT_SERVICES, BaseGitService
from macaron.slsa_analyzer.git_service.base_git_service import NoneGitService
from macaron.slsa_analyzer.git_url import GIT_REPOS_DIR

logger: logging.Logger = logging.getLogger(__name__)


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
    try:
        purl_object = PackageURL.from_string(purl)
    except ValueError as error:
        logger.debug("Failed to parse purl string as PURL: %s", error)
        return False

    report_json = create_report(purl, commit, repo)

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


def create_report(purl: str, commit: str, repo: str) -> str:
    """Generate report for standalone uses of the repo / commit finder.

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
        The report as a JSON string.
    """
    data = {"purl": purl, "commit": commit, "repo": repo, "repo_validated": False, "commit_validated": False, "url": ""}
    if urlparse(repo).hostname == "github.com":
        data["url"] = f"{repo}/commit/{commit}"
    return json.dumps(data, indent=4)


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


def check_repo_urls_are_equivalent(repo_1: str, repo_2: str) -> bool:
    """Check if the two passed repo URLs are equivalent.

    Parameters
    ----------
    repo_1: str
        The first repository URL as a string.
    repo_2: str
        The second repository URL as a string.

    Returns
    -------
    bool
        True if the repository URLs have equal hostnames and paths, otherwise False.
    """
    repo_url_1 = urlparse(repo_1)
    repo_url_2 = urlparse(repo_2)
    if repo_url_1.hostname != repo_url_2.hostname or repo_url_1.path != repo_url_2.path:
        return False

    return True
