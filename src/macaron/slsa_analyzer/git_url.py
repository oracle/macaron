# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides methods to perform generic actions on Git URLS."""


import logging
import os
import re
import string
import urllib.parse
from configparser import ConfigParser

from git import GitCommandError
from git.objects import Commit
from git.remote import Remote
from git.repo import Repo
from pydriller.git import Git

from macaron.config.defaults import defaults
from macaron.errors import CloneError

logger: logging.Logger = logging.getLogger(__name__)


def reset_git_repo(git_obj: Git, stash: bool = True, index: bool = True, working_tree: bool = True) -> bool:
    """Reset the index and working tree of the target repository.

    Note that this method does not reset any untracked or ignored files.

    Parameters
    ----------
    git_obj : Git
        The pydriller.Git object of the repository.
    stash : bool
        If True, any uncommitted changes will be stashed.
    index : bool
        If True, the index of the repository will be reset.
    working_tree : bool
        If True, the working tree will be forcefully adjusted to match HEAD, possibly overwriting uncommitted changes.
        If working_tree is True, index must be true as well.

    Returns
    -------
    bool
        True if no errors encountered, else False.
    """
    try:
        if stash:
            logger.info("Stashing any uncommitted changes.")
            stash_out = git_obj.repo.git.stash(message="Stashing uncommitted changes by Macaron.")
            logger.debug("\t Git CMD output: %s", stash_out)

        logger.info("Forcefully reset the repository.")
        git_obj.repo.head.reset(index=index, working_tree=working_tree)
        return True
    except GitCommandError as error:
        logger.error("Error while trying to reset untracked changes in the repository: %s", error)
        return False
    except ValueError as error:
        logger.error(error)
        return False


def check_out_repo_target(git_obj: Git, branch_name: str = "", digest: str = "", offline_mode: bool = False) -> bool:
    """Checkout the branch and commit specified by the user.

    If no branch name is provided, this method will checkout the default branch
    of the repository and analyze the latest commit from remote. Note that checking out the branch
    is always performed before checking out the specific ``digest`` (if provided).

    If ``digest`` is not provided, this method always pulls (fast-forward only) and checks out the latest commit.

    If ``digest`` is provided, this method will checkout that specific commit. If ``digest``
    cannot be found in the current branch, this method will pull (fast-forward only) from remote.

    This method supports repositories which are cloned (full or shallow) from existing remote repositories.
    Other scenarios are not covered (e.g. a newly initiated repository).

    If ``offline_mode`` is set, this method will not pull from remote while checking out the branch or commit.

    Parameters
    ----------
    git_obj : Git
        The pydriller.Git wrapper object of the target repository.
    branch_name : str
        The name of the branch we want to checkout.
    digest : str
        The hash of the commit that we want to checkout in the branch.
    offline_mode : bool
        If True, this function will not perform any online operation (fetch, pull).

    Returns
    -------
    bool
        True if succeed else False.
    """
    # Resolve the branch name to check out.
    res_branch = ""
    if branch_name:
        res_branch = branch_name
    else:
        res_branch = get_default_branch(git_obj)
        if not res_branch:
            logger.error("Cannot determine the default branch for this repository.")
            logger.info("Consider providing the specific branch to be analyzed or fully cloning the repo instead.")
            return False

    # Checkout the resolved branch from remote origin.
    # The name of each remote ref will be in the form <prefix>/<name> (e.g. origin/master).
    # We only work with origin remote in Macaron.
    try:
        org_remote: Remote = git_obj.repo.remote("origin")
    except ValueError as error:
        logger.error("Cannot get origin remote from the repository.")
        logger.error(error)
        return False

    if not org_remote or not hasattr(org_remote, "refs"):
        logger.critical("The origin remote does not exist or does not have the references attribute.")
        return False

    if res_branch in [os.path.basename(ref.name) for ref in org_remote.refs]:
        logger.info(
            "Find branch %s in the remote's refs of the local repository. The branch is checked out directly.",
            res_branch,
        )
        git_obj.repo.git.checkout(res_branch)
    else:
        # This might happen because the git repository is a shallow clone.
        logger.info("Cannot find branch %s. Try to fetch the branch from remote.", res_branch)
        try:
            # Trying to get this branch by fetching from remote and checkout the branch again.
            # If we can't checkout, we consider that this branch does not exist.
            # https://stackoverflow.com/questions/23708231/git-shallow-clone-clone-depth-misses-remote-branches.
            git_obj.repo.git.remote("set-branches", "--add", "origin", res_branch)
            org_remote.fetch(res_branch)
            git_obj.repo.git.checkout(res_branch)
        except GitCommandError as error:
            logger.error("Error while getting branch %s. Error: %s", res_branch, error)
            return False

    logger.info("Successfully checked out branch %s.", res_branch)

    # We only pull the latest changes if we are not running in offline mode and:
    #   - no digest is provided.
    #   - or a commit digest is provided but it does not exist in the current local branch.
    if not offline_mode and (not digest or not commit_exists(git_obj, digest)):
        logger.info("Pulling the latest changes of branch %s fast-forward only.", res_branch)
        if not pull_latest_changes(git_obj):
            logger.error(
                "Cannot pull the latest changes for branch %s.",
                res_branch,
            )
            return False

    if digest:
        current_head: Commit = git_obj.repo.head.commit
        # We don't return False if current_head is None here to try checking out the
        # specific commit by the user.
        if current_head and current_head.hexsha == digest:
            logger.info("HEAD of the repo is already at %s.", digest)
            return True

        # Check if the commit exist in the history after we have pulled the latest changes.
        if commit_exists(git_obj, digest):
            # The digest was found in the history of the branch.
            try:
                git_obj.checkout(digest)
            except GitCommandError as error:
                logger.error(
                    "Commit %s cannot be checked out. Error: %s",
                    digest,
                    error,
                )
                return False
        else:
            logger.info("Cannot find commit %s on branch %s. Please check the configuration.", digest, res_branch)
            return False

    final_head_commit: Commit = git_obj.repo.head.commit
    if not final_head_commit:
        logger.critical("Cannot get the head commit after checking out.")
        return False

    if digest and final_head_commit.hexsha != digest:
        logger.critical("The current HEAD at %s. Expect %s.", final_head_commit.hexsha, digest)
        return False

    logger.info("Successfully checked out commit %s.", final_head_commit.hexsha)
    return True


def commit_exists(git_obj: Git, digest: str) -> bool:
    """Return True if the commit exists in the history of the current branch.

    Parameters
    ----------
    git_obj : Git
        The pydriller.Git wrapper object of the target repository.
    digest : str
        The hash of the commit that we want to check.

    Returns
    -------
    bool
    """
    try:
        return bool(git_obj.repo.is_ancestor(digest, "HEAD"))
    except GitCommandError as error:
        # The exception could be raised because the digest does not exist in the history of the branch
        # or the digest is not a valid digest.
        logger.debug(error)
        return False


def pull_latest_changes(git_obj: Git) -> bool:
    """Pull the latest changes from remote.

    This will perform git pull --ff-only on the current active branch of ``git_obj``. This will
    leave HEAD pointing to the latest commit of the current branch.

    If the repo is a shallow clone, this method will unshallow it before pulling the
    latest changes.

    Parameters
    ----------
    git_obj : Git
        The pydriller.Git wrapper object of the target repository.

    Returns
    -------
    bool
        True if successful, else False.
    """
    try:
        # Handle the case when the repository is a shallow cloned.
        # https://git-scm.com/docs/git-rev-parse#Documentation/git-rev-parse.txt---is-shallow-repository
        if str(git_obj.repo.git.rev_parse("--is-shallow-repository")).strip() == "true":
            logger.info("The repository is a shallow clone. Trying to unshallow it.")
            git_obj.repo.git.fetch("--unshallow")

        # Pull the latest changes on the current branch fast-forward only.
        git_obj.repo.git.pull("-f", "--ff-only")
        return True
    except GitCommandError as error:
        logger.error(error)
        return False


def get_default_branch(git_obj: Git) -> str:
    """Return the default branch of the target repository.

    This function does not perform any online operation.

    Parameters
    ----------
    git_obj : Git
        The pydriller.Git wrapper object of the target repository.

    Returns
    -------
    str
        The default branch name or empty if errors.
    """
    try:
        # https://stackoverflow.com/questions/28666357/git-how-to-get-default-branch
        # This command will return origin/<default-branch-name>.
        # It can also work after we checkout a specific commit making HEAD into a detached state.
        # This is suitable for running multiple times on a repo.
        default_branch_full: str = git_obj.repo.git.rev_parse("--abbrev-ref", "origin/HEAD")
        return default_branch_full[7:]
    except GitCommandError as error:
        logger.error("Error when getting default branch. Error: %s", error)
        return ""


def is_remote_repo(path_to_repo: str) -> bool:
    """Verify if the given repository path is a remote path.

    Parameters
    ----------
    path_to_repo : str
        The path of the repository to check.

    Returns
    -------
    bool
        True if it's a remote path else return False.
    """
    # Validate the url.
    parsed_url = get_remote_vcs_url(path_to_repo)
    if parsed_url == "":
        logger.debug("URL '%s' is not valid.", path_to_repo)
        return False
    return True


def clone_remote_repo(clone_dir: str, url: str) -> Repo | None:
    """Clone the remote repository and return the `git.Repo` object for that repository.

    If there is an existing non-empty ``clone_dir``, Macaron assumes the repository has
    been cloned already and cancels the clone.
    This could happen when multiple runs of Macaron use the same `<output_dir>`, leading
    to Macaron potentially trying to clone a repository multiple times.

    Parameters
    ----------
    clone_dir : str
        The directory to clone the repo to.
    url : str
        The url to clone the repository.
        Important: this can contain secrets! (e.g. cloning with GitLab token)

    Returns
    -------
    git.Repo | None
        The ``git.Repo`` object of the repository, or ``None`` if the clone directory already exists.

    Raises
    ------
    CloneError
        If the repository has not been cloned and the clone attempt fails.
    """
    # Handle the case where the repository already exists in `<output_dir>/git_repos`.
    # This could happen when multiple runs of Macaron use the same `<output_dir>`, leading to
    # Macaron attempting to clone a repository multiple times.
    # In these cases, we should not error since it may interrupt the analysis.
    if os.path.isdir(clone_dir):
        try:
            os.rmdir(clone_dir)
            logger.debug("The clone dir %s is empty. It has been deleted for cloning the repo.", clone_dir)
        except OSError:
            logger.debug(
                "The clone dir %s is not empty. Cloning will not be proceeded.",
                clone_dir,
            )
            return None

    try:
        # The Repo.clone_from method handles creating intermediate dirs.
        return Repo.clone_from(
            url=url,
            to_path=clone_dir,
            env={
                # Setting the GIT_TERMINAL_PROMPT environment variable to ``0`` stops
                # ``git clone`` from prompting for login credentials.
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
    except GitCommandError as error:
        # stderr here does not contain secrets, so it is safe for logging.
        raise CloneError(error.stderr) from None


def get_repo_name_from_url(url: str) -> str:
    """Extract the repo name of the repository from the remote url.

    Parameters
    ----------
    url : str
        The remote url of the repository.

    Returns
    -------
    str
        The name of the repository or an empty string if errors.

    Examples
    --------
    >>> get_repo_name_from_url("https://github.com/owner/repo")
    'repo'
    """
    full_name = get_repo_full_name_from_url(url)
    if not full_name:
        logger.error("Cannot extract repo name if we cannot extract the fullname of %s.", url)
        return ""

    return full_name.split("/")[1]


def get_repo_full_name_from_url(url: str) -> str:
    """Extract the full name of the repository from the remote url.

    The full name is in the form <owner>/<name>. Note that this function assumes `url` is a remote url.

    Parameters
    ----------
    url : str
        The remote url of the repository.

    Returns
    -------
    str
        The full name of the repository or an empty string if errors.
    """
    # Parse the remote url.
    parsed_url = parse_remote_url(url)
    if not parsed_url:
        logger.debug("URL '%s' is not valid.", url)
        return ""

    full_name = parsed_url.path.split(".git")[0]

    # The full name must be in org/repo format
    if len(full_name.split("/")) != 2:
        logger.error("Fullname %s extract from %s is not valid.", full_name, url)
        return ""

    return full_name


def get_repo_complete_name_from_url(url: str) -> str:
    """Return the complete name of the repo from a remote repo url.

    The complete name will be in the form ``<git_host>/org/name``.

    Parameters
    ----------
    url: str
        The remote url of the target repository.

    Returns
    -------
    str
        The unique path resolved from the remote path or an empty string if errors.

    Examples
    --------
    >>> get_repo_complete_name_from_url("github.com/apache/maven")
    'github.com/apache/maven'
    """
    remote_url = get_remote_vcs_url(url)
    if not remote_url:
        logger.debug("URL '%s' is not valid.", url)
        return ""

    parsed_url = parse_remote_url(remote_url)
    if not parsed_url:
        # Shouldn't happen.
        logger.critical("URL '%s' is not valid even though it has been validated.", url)
        return ""

    git_host = parsed_url.netloc
    return os.path.join(git_host, parsed_url.path.strip("/"))


def get_remote_origin_of_local_repo(git_obj: Git) -> str:
    """Get the origin remote of a repository.

    Note that this origin remote can be either a remote url or a path to a local repo.

    Parameters
    ----------
    git_obj : Git
        The pydriller.Git object of the repository.

    Returns
    -------
    str
        The origin remote path or empty if error.
    """
    try:
        remote_origin = git_obj.repo.remote("origin")
        remote_urls = [*remote_origin.urls]
        remote_urls.sort()
        valid_remote_path_set = {value for value in remote_urls if value != ""}
    except ValueError as error:
        logger.error("No origin remote discovered for the repository: %s", error)
        return ""

    # This path could be either a remote path or a local path (if the repo is cloned from another local repo or from
    # a git bundle).
    # We don't need to validate this path as we are getting it from an already cloned repository. If the path is invalid
    # it should have been caught during the preparing process of the git repository.
    remote_origin_path = valid_remote_path_set.pop()

    # Hide the GitLab OAuth token from the repo's remote.
    # This is because cloning from GitLab with an access token requires us to embed
    # the token in the URL.
    if "oauth2" in remote_origin_path:
        try:
            url_parse_result = urllib.parse.urlparse(remote_origin_path)
        except ValueError:
            logger.error("Error occurs while processing the remote URL of repo %s.", git_obj.project_name)
            return ""

        _, _, domain = url_parse_result.netloc.rpartition("@")

        new_url_parse_result = urllib.parse.ParseResult(
            scheme=url_parse_result.scheme,
            netloc=domain,
            path=url_parse_result.path,
            params=url_parse_result.params,
            query=url_parse_result.query,
            fragment=url_parse_result.fragment,
        )
        remote_origin_path = urllib.parse.urlunparse(new_url_parse_result)

    return remote_origin_path or ""


def clean_up_repo_path(repo_path: str) -> str:
    """Clean up the repo path.

    This method returns the repo path after cleaning up.

    Parameters
    ----------
    repo_path : str
        The repo path to clean up.

    Returns
    -------
    str
        The cleaned up repo path.
    """
    cleaned_path = repo_path.strip(" ").rstrip("/")
    return cleaned_path[:-4] if cleaned_path.endswith(".git") else cleaned_path


def get_remote_vcs_url(url: str, clean_up: bool = True) -> str:
    """Verify if the given repository path is a valid vcs.

    We support some of the patterns listed in https://git-scm.com/docs/git-clone#_git_urls.

    Parameters
    ----------
    url : str
        The path of the repository to check.
    clean_up : bool
        Set to True to clean up the returned remote url (default: True).

    Returns
    -------
    str
        The remote url to the repo or empty if the url is invalid.
    """
    parsed_result = parse_remote_url(url)
    if not parsed_result:
        return ""

    url_as_str = urllib.parse.urlunparse(parsed_result)

    if clean_up:
        return clean_up_repo_path(url_as_str)

    return url_as_str


def parse_remote_url(url: str, allowed_git_service_domains: list[str] | None = None) -> urllib.parse.ParseResult | None:
    """Verify if the given repository path is a valid vcs.

    This method converts the url to a ``https://`` url and return a
    ``urllib.parse.ParseResult object`` to be consumed by Macaron.
    Note that the port number in the original url will be removed.

    Parameters
    ----------
    url: str
        The path of the repository to check.
    allowed_git_service_domains: list[str] | None
        The list of allowed git service domains.
        If this is ``None``, fall back to the  ``.ini`` configuration.
        (Default: None).

    Returns
    -------
    urllib.parse.ParseResult | None
        The parse result of the url or None if errors.

    Examples
    --------
    >>> parse_remote_url("ssh://git@github.com:7999/owner/org.git")
    ParseResult(scheme='https', netloc='github.com', path='owner/org.git', params='', query='', fragment='')
    """
    if allowed_git_service_domains is None:
        allowed_git_service_domains = get_allowed_git_service_domains(defaults)

    try:
        # Remove prefixes, such as "scm:" and "git:".
        match = re.match(r"(?P<prefix>(.*?))(git\+http|http|ftp|ssh\+git|ssh|git@)(.)*", str(url))
        if match is None:
            return None
        cleaned_url = url.replace(match.group("prefix"), "")

        # Parse the URL string to determine how to handle it.
        parsed_url = urllib.parse.urlparse(cleaned_url)
    except (ValueError, TypeError) as error:
        logger.debug(error)
        return None

    res_scheme = ""
    res_path = ""
    res_netloc = ""

    # e.g., https://github.com/owner/project.git
    if parsed_url.scheme in ("http", "https", "ftp", "ftps", "git+https"):
        if parsed_url.netloc not in allowed_git_service_domains:
            return None
        path_params = parsed_url.path.strip("/").split("/")
        if len(path_params) < 2:
            return None

        res_path = "/".join(path_params[:2])
        res_scheme = "https"
        res_netloc = parsed_url.netloc

    # e.g.:
    #   ssh://git@hostname:port/owner/project.git
    #   ssh://git@hostname:owner/project.git
    elif parsed_url.scheme in ("ssh", "git+ssh"):
        user_host, _, port = parsed_url.netloc.partition(":")
        user, _, host = user_host.rpartition("@")

        if not user or host not in allowed_git_service_domains:
            return None

        path = ""
        if not port.isdecimal():
            # Happen for ssh://git@github.com:owner/project.git
            # where parsed_url.netloc="git@github.com:owner", port="owner"
            # and parsed_url.path="project.git".
            # In this case, we merge port with parsed_url.path
            # to get the full path.
            path = f"{port}/{parsed_url.path.strip('/')}"
        else:
            path = parsed_url.path

        path_params = path.strip("/").split("/")
        if len(path_params) < 2:
            return None

        res_path = f"{path_params[0]}/{path_params[1]}"
        res_scheme = "https"
        res_netloc = host

    # e.g., git@github.com:owner/project.git
    elif parsed_url.scheme == "":
        user_host, _, port_path = parsed_url.path.partition(":")
        if not user_host or not port_path:
            return None
        user, _, host = user_host.rpartition("@")
        if not user or host not in allowed_git_service_domains:
            return None

        path = ""
        port_num, _, path_remain = port_path.strip("/").partition("/")
        if not port_num.isdecimal():
            # port_path doesn't have any port number (e.g. port_path == /org/name).
            # We use all of port_path as the path.
            path = port_path
        else:
            # port_path have valid port number (e.g. port_path == 7999/org/name).
            # We only use the rest of the path.
            path = path_remain

        path_params = path.strip("/").split("/")
        if len(path_params) < 2:
            return None

        res_path = f"{path_params[0]}/{path_params[1]}"
        res_scheme = "https"
        res_netloc = host

    try:
        return urllib.parse.ParseResult(
            scheme=res_scheme,
            netloc=res_netloc,
            path=res_path,
            params="",
            query="",
            fragment="",
        )
    except ValueError:
        logger.debug("Could not reconstruct %s.", url)
        return None


def get_allowed_git_service_domains(config: ConfigParser) -> list[str]:
    """Load allowed git service domains from ini configuration.

    Some notes for future improvements:

    The fact that this method is here is not ideal.

    Q: Why do we need this method here in this ``git_url`` module in the first place?
    A: A number of functions in this module also do "URL validation" as part of their logic.
    This requires loading in the allowed git service domains from the ini config.

    Q: Why don't we use the ``GIT_SERVICES`` list from the ``macaron.slsa_analyzer.git_service``
    instead of having this second place of loading git service configuration?
    A: Referencing ``GIT_SERVICES`` in this module results in cyclic imports since the module
    where ``GIT_SERVICES`` is defined in also reference this module.
    """
    git_service_section_names = [
        section_name for section_name in config.sections() if section_name.startswith("git_service")
    ]

    allowed_git_service_domains = []

    for section_name in git_service_section_names:
        git_service_section = config[section_name]

        domain = git_service_section.get("domain")
        if not domain:
            continue

        allowed_git_service_domains.append(domain)

    return allowed_git_service_domains


def get_repo_dir_name(url: str, sanitize: bool = True) -> str:
    """Return the repo directory name from a remote repo url.

    The directory name will be in the form ``<git_host>/org/name``.
    When sanitize is True (default), this method
    makes sure that ``git_host`` is a valid directory name:
    - Contains only lowercase letters and numbers
    - Only starts with lowercase letters or numbers
    - Words are separated by ``_``

    Parameters
    ----------
    url: str
        The remote url of the target repository.
    sanitize: bool
        Sanitizes the name to be a valid directory name (Default True)

    Returns
    -------
    str
        The unique path resolved from the remote path or an empty string if errors.

    Examples
    --------
    >>> get_repo_dir_name("https://github.com/apache/maven")
    'github_com/apache/maven'
    """
    remote_url = get_remote_vcs_url(url)
    if not remote_url:
        logger.debug("URL '%s' is not valid.", url)
        return ""

    parsed_url = parse_remote_url(remote_url)
    if not parsed_url:
        # Shouldn't happen.
        logger.critical("URL '%s' is not valid even though it has been validated.", url)
        return ""

    git_host = parsed_url.netloc

    if not sanitize:
        return os.path.join(git_host, parsed_url.path.strip("/"))

    # Sanitize the path and make sure it's a valid directory name.
    allowed_chars = string.ascii_lowercase + string.digits
    for letter in git_host:
        if letter not in allowed_chars:
            git_host = git_host.replace(letter, "_", 1)

    # Cannot start with _.
    if git_host.startswith("_"):
        git_host = f"mcn{git_host}"

    return os.path.join(git_host, parsed_url.path.strip("/"))


def is_empty_repo(git_obj: Git) -> bool:
    """Return True if the repo has no commit checked out.

    Parameters
    ----------
    git_obj : Git
        The pydriller.Git object of the repository.

    Returns
    -------
    bool
        True if the repo has no commit else False.
    """
    # https://stackoverflow.com/questions/5491832/how-can-i-check-whether-a-git-repository-has-any-commits-in-it
    try:
        head_commit_hash = git_obj.repo.git.rev_parse("HEAD")
        if not head_commit_hash:
            return True

        return False
    except GitCommandError:
        return True
