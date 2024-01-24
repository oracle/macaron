# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The module provides API clients for VCS services, such as GitHub."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from enum import Enum
from typing import NamedTuple

from macaron.config.defaults import defaults
from macaron.slsa_analyzer.asset import AssetLocator
from macaron.util import construct_query, download_github_build_log, send_get_http, send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class GitHubReleaseAsset(NamedTuple):
    """An asset published from a GitHub Release."""

    #: The asset name.
    name: str
    #: The URL to the asset.
    url: str
    #: The size of the asset, in bytes.
    size_in_bytes: int
    #: The GitHub API client.
    api_client: GhAPIClient

    def download(self, dest: str) -> bool:
        """Download the asset.

        Parameters
        ----------
        dest : str
            The local destination where the asset is downloaded to.
            Note that this must include the file name.

        Returns
        -------
        bool
            ``True`` if the asset is downloaded successfully; ``False`` if not.
        """
        return self.api_client.download_asset(self.url, dest)


class BaseAPIClient:
    """This is the base class for API clients."""

    # TODO: refactor API clients.

    def get_latest_release(self, full_name: str) -> dict:  # pylint: disable=unused-argument
        """Return the latest release for the repo.

        Parameters
        ----------
        full_name : str
            The full name of the repo.

        Returns
        -------
        dict
            The latest release object in JSON format.
        """
        return {}

    def fetch_assets(self, release: dict, ext: str = "") -> Sequence[AssetLocator]:  # pylint: disable=unused-argument
        """Return the release assets that match or empty if it doesn't exist.

        The extension is ignored if name is set.

        Parameters
        ----------
        release : dict
            The release object in JSON format.
        ext : str
            The asset extension to find; this parameter is ignored if name is set.

        Returns
        -------
        list[dict]
            The list of release assets that match or empty if it doesn't exist.
        """
        return []

    def download_asset(self, url: str, download_path: str) -> bool:  # pylint: disable=unused-argument
        """Download the assets of the release that match the pattern (if specified).

        Parameters
        ----------
        url : dict
            The release URL.
        download_path : str
            The path to download assets.

        Returns
        -------
        bool
            Returns True if successful and False otherwise.
        """
        return False

    # pylint: disable=unused-argument
    def get_file_link(self, full_name: str, commit_sha: str, file_path: str) -> str:
        """Return a hyperlink to the file.

        Parameters
        ----------
        full_name : str
            The full name of the repository.
        commit_sha : str
            The sha checksum of the commit that file belongs to.
        file_path : str
            The relative path of the file to the root dir of the repository.

        Returns
        -------
        str
            The hyperlink tag to the file.
        """
        return ""

    def get_relative_path_of_workflow(self, workflow_name: str) -> str:  # pylint: disable=unused-argument
        """Return the relative path of the workflow from the root dir of the repo.

        Parameters
        ----------
        workflow_name : str
            The name of the CI configuration file.

        Returns
        -------
        str
            The relative path of the CI configuration file from the root dir of the repo.
        """
        return ""


class _GhAPIEndPoint(Enum):
    """The end points of the GitHub REST API."""

    SEARCH = "search"
    """The Search API lets you to search for specific items on GitHub."""
    REPO = "repos"
    """The Repos API allows to create, manage and control the workflow of public and private GitHub repositories."""


class GhAPIClient(BaseAPIClient):
    """This class acts as a client to use GitHub API.

    See https://docs.github.com/en/rest for the GitHub API documentation.
    """

    _GH_API_URL = "https://api.github.com"
    _SEARCH_END_POINT = f"{_GH_API_URL}/{_GhAPIEndPoint.SEARCH.value}"
    _REPO_END_POINT = f"{_GH_API_URL}/{_GhAPIEndPoint.REPO.value}"

    def __init__(self, profile: dict):
        """Initialize GHSearchClient.

        Parameters
        ----------
        profile : dict
            The json object describes the profile to be included
            in each request by this client.
        """
        super().__init__()
        self.headers = profile["headers"]
        self.query_list = profile["query"]

    def get_repo_workflow_data(self, full_name: str, workflow_name: str) -> dict:
        """Query GitHub REST API for the information of a workflow.

        The url would be in the following form:
        ``https://api.github.com/repos/{full_name}/actions/workflows/{workflow_name}``

        Parameters
        ----------
        full_name : str
            The full name of the target repo in the form ``owner/repo``.
        workflow_name : str
            The full name of the workflow YAML file.

        Returns
        -------
        dict
            The json query result or an empty dict if failed.

        Examples
        --------
        The following call to this method will perform a query to
        ``https://api.github.com/repos/owner/repo/actions/workflows/build.yml``

        .. code-block: python3

            gh_client.get_repo_workflow_data(
                full_name="owner/repo",
                workflow_name="build.yml",
            )
        """
        logger.debug("Query for %s workflow in repo %s", workflow_name, full_name)
        url = f"{GhAPIClient._REPO_END_POINT}/{full_name}/actions/workflows/{workflow_name}"
        response_data = send_get_http(url, self.headers)

        return response_data

    def get_workflow_runs(
        self, full_name: str, branch_name: str | None = None, created_after: str | None = None, page: int = 1
    ) -> dict:
        """Query the GitHub REST API for the data of all workflow run of a repository.

        The url would be in the following form:
        ``https://api.github/com/repos/{full_name}/
        actions/runs?{page}&branch={branch_name}&created=>={created_after}&per_page={MAX_ITEMS_NUM}``

        The ``branch_name`` and ``commit_date`` parameters can be empty. ``MAX_ITEMS_NUM`` can be configured via
        the defaults.ini.

        Parameters
        ----------
        full_name : str
            The full name of the target repo in the form ``owner/repo``.
        branch_name : str | None
            The name of the branch to look for workflow runs (e.g ``master``).
        created_after : str
            Only look for workflow runs after this date (e.g. ``2022-03-11T16:44:40Z``).
        page : int
            The page number for querying as the workflow we want to get might be in
            a different page (due to max limit 100 items per page).

        Returns
        -------
        dict
            The json query result or an empty dict if failed.

        Examples
        --------
        The following call to this method will perform a query to
        ``https://api.github/com/repos/owner/repo/actions/runs?1&branch=master&created=>=
        2022-03-11T16:44:40Z&per_page=100``

        .. code-block: python3

            gh_client.get_workflow_runs(
                full_name="owner/repo",
                branch_name="master",
                created_after="2022-03-11T16:44:40Z",
                page=1,
            )
        """
        logger.debug("Query for runs data in repo %s", full_name)
        query_params: dict = {
            "page": page,
            "per_page": defaults.getint("ci.github_actions", "max_items_num", fallback=100),
        }

        # We assume that workflow run only happens after the commit date.
        # https://docs.github.com/en/rest/reference/actions#list-workflow-runs-for-a-repository
        if branch_name:
            query_params["branch"] = branch_name

        if created_after:
            query_params["created"] = f">={created_after}"

        encoded_params = construct_query(query_params)
        url = f"{GhAPIClient._REPO_END_POINT}/{full_name}/actions/runs?" + encoded_params
        response_data = send_get_http(url, self.headers)

        return response_data

    def get_workflow_run_jobs(self, full_name: str, run_id: str) -> dict:
        """Query the GitHub REST API for the workflow run jobs.

        The url would be in the following form:
        ``https://api.github/com/repos/{full_name}/actions/runs/<run_id>/jobs``

        Parameters
        ----------
        full_name : str
            The full name of the target repo in the form ``owner/repo``.
        run_id : str
            The target workflow run ID.

        Returns
        -------
        dict
            The json query result or an empty dict if failed.

        Examples
        --------
        The following call to this method will perform a query to
        ``https://api.github/com/repos/{full_name}/
        actions/runs/<run_id>/jobs``

        .. code-block: python3

            gh_client.get_workflow_run_jobs(
                full_name="owner/repo",
                run_id=<run_id>,
            )
        """
        logger.debug("Query GitHub to get run jobs for %s with run ID %s", full_name, run_id)

        url = f"{GhAPIClient._REPO_END_POINT}/{full_name}/actions/runs/{run_id}/jobs"
        response_data = send_get_http(url, self.headers)

        return response_data

    def get_workflow_run_for_date_time_range(self, full_name: str, datetime_range: str) -> dict:
        """Query the GitHub REST API for the workflow run within a datetime range.

        The url would be in the following form:
        ``https://api.github.com/repos/{full_name}/actions/runs?create=datetime-range``

        Parameters
        ----------
        full_name : str
            The full name of the target repo in the form ``owner/repo``.
        datetime_range : str
            The datetime range to query.

        Returns
        -------
        dict
            The json query result or an empty dict if failed.

        Examples
        --------
        The following call to this method will perform a query to
        ``https://api.github/com/repos/owner/repo/actions/runs?created=2022-11-05T20:38:40..2022-11-05T20:38:58``

        .. code-block: python3

            gh_client.get_workflow_run_for_date_time_range(
                full_name="owner/repo",
                created=2022-11-05T20:38:40..2022-11-05T20:38:58,
            )
        """
        logger.debug("Query GitHub to get run details for %s at %s", full_name, datetime_range)
        query_params = {"created": datetime_range}

        encoded_params = construct_query(query_params)
        url = f"{GhAPIClient._REPO_END_POINT}/{full_name}/actions/runs?" + encoded_params
        response_data = send_get_http(url, self.headers)

        return response_data

    def get_commit_data_from_hash(self, full_name: str, commit_hash: str) -> dict:
        """Query the GitHub API for the data of a commit using the hash for that commit.

        The url would be in the following form:
        ``https://api.github.com/repos/{full_name}/commits/{commit_hash}``

        Parameters
        ----------
        full_name : str
            The full name of the repository in the format {owner/name}.
        commit_hash : str
            The sha commit hash of the target commit.

        Returns
        -------
        dict
            The json query result or an empty dict if failed.

        Examples
        --------
        The following call to this method will perform a query to:
        ``https://api.github.com/repos/owner/repo/commits/6dcb09b5b57875f334f61aebed695e2e4193db5e``

        .. code-block:: python3

            gh_client.get_commit_data_from_hash(
                full_name="owner/repo",
                commit_hash="6dcb09b5b57875f334f61aebed695e2e4193db5e",
            )
        """
        logger.debug("Query for commit %s 's data in repo %s", commit_hash, full_name)
        url = f"{GhAPIClient._REPO_END_POINT}/{full_name}/commits/{commit_hash}"
        response_data = send_get_http(url, self.headers)

        return response_data

    def search(self, target: str, query: str) -> dict:
        """Perform a search using GitHub REST API.

        This query is at endpoint:
        ``api.github.com/search/{target}?{query}``

        Parameters
        ----------
        target : str
            The search target.
        query : str
            The query string.

        Returns
        -------
        dict
            The json query result or an empty dict if failed.

        Examples
        --------
        The following call to this method will perform a query to:
        ``https://api.github.com/search/code?q=addClass+in:file+language:js+repo:jquery/jquery``

        .. code-block:: python3

            gh_client.search(
                target="repositories",
                query="q=addClass+in:file+language:js+repo:jquery/jquery",
            )
        """
        logger.debug("Search %s with query: %s", target, query)
        url = f"{GhAPIClient._SEARCH_END_POINT}/{target}?{query}"
        response_data = send_get_http(url, self.headers)

        return response_data

    def get(self, url: str) -> dict:
        """Perform a GET request to the given URL.

        Parameters
        ----------
        url : str
            The url to send the GET request.

        Returns
        -------
        dict
            The json query result or an empty dict if failed.
        """
        return send_get_http(url, self.headers)

    def get_job_build_log(self, log_url: str) -> str:
        """Download and return the build log indicated at `log_url`.

        Parameters
        ----------
        log_url : str
            The link to get the build log from GitHub API.

        Returns
        -------
        str
            The whole build log in str.
        """
        return download_github_build_log(log_url, self.headers)

    def get_repo_data(self, full_name: str) -> dict:
        """Get the repo data using GitHub REST API.

        The query is at endpoint:
        ``api.github.com/repos/{full_name}``

        Parameters
        ----------
        full_name : str
            The full name of the repository in the format {owner/name}.

        Returns
        -------
        dict:
            The json query result or an empty dict if failed.

        Examples
        --------
        To get the repo data from repository ``apache/maven``:

        .. code-block:: python3

            gh_client.get_repo_data("apache/maven")
        """
        logger.debug("Get data of repository %s", full_name)
        url = f"{GhAPIClient._REPO_END_POINT}/{full_name}"
        response_data = send_get_http(url, self.headers)

        return response_data

    def get_file_link(self, full_name: str, commit_sha: str, file_path: str) -> str:
        """Return a GitHub hyperlink tag or just a link to the file.

        The format for the link is `https://github.com/{full_name}/blob/{digest}/{file_path}`.
        The path of the file is relative to the root dir of the repository. The commit
        sha must be in full form.

        Parameters
        ----------
        full_name : str
            The full name of the repository in the format {owner/name}.
        commit_sha : str
            The sha checksum of the commit that file belongs to.
        file_path : str
            The relative path of the file to the root dir of the repository.

        Returns
        -------
        str
            The hyperlink tag to the file.

        Examples
        --------
        >>> api_client = GhAPIClient(profile={"headers": "", "query": []})
        >>> api_client.get_file_link("owner/repo", "5aaaaa43caabbdbc26c254df8f3aaa7bb3f4ec01", ".travis_ci.yml")
        'https://github.com/owner/repo/blob/5aaaaa43caabbdbc26c254df8f3aaa7bb3f4ec01/.travis_ci.yml'
        """
        return f"https://github.com/{full_name}/blob/{commit_sha}/{file_path}"

    def get_relative_path_of_workflow(self, workflow_name: str) -> str:
        """Return the relative path of the workflow from the root dir of the repo.

        Parameters
        ----------
        workflow_name : str
            The name of the yaml Gh Action workflow.

        Returns
        -------
        str
            The relative path of the workflow from the root dir of the repo.

        Examples
        --------
        >>> api_client = GhAPIClient(profile={"headers": "", "query": []})
        >>> api_client.get_relative_path_of_workflow("build.yaml")
        '.github/workflows/build.yaml'
        """
        return f".github/workflows/{workflow_name}"

    def get_latest_release(self, full_name: str) -> dict:
        """Return the latest release for the repo.

        Parameters
        ----------
        full_name : str
            The full name of the repo.

        Returns
        -------
        dict
            The latest release object in JSON format.
            Schema: https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28#get-the-latest-release.
        """
        logger.debug("Get the latest release for %s.", full_name)
        url = f"{GhAPIClient._REPO_END_POINT}/{full_name}/releases/latest"
        response_data = send_get_http(url, self.headers)

        return response_data or {}

    def fetch_assets(self, release: dict, ext: str = "") -> Sequence[AssetLocator]:
        """Return the release assets that match or empty if it doesn't exist.

        The extension is ignored if name is set.

        Parameters
        ----------
        release : dict
            The release payload in JSON format.
            Schema: https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28#get-the-latest-release.
        ext : str
            The asset extension to find; this parameter is ignored if name is set.

        Returns
        -------
        Sequence[AssetLocator]
            A sequence of release assets.
        """
        assets = release.get("assets", [])
        if not isinstance(assets, list):
            return []

        asset_locators = []

        for asset in assets:
            name = asset.get("name")
            if name is None or not isinstance(name, str):
                continue

            if ext and not name.endswith(ext):
                continue

            url = asset.get("url")
            if url is None or not isinstance(url, str):
                continue

            size_in_bytes = asset.get("size")
            if size_in_bytes is None or not isinstance(size_in_bytes, int):
                continue

            asset_locators.append(
                GitHubReleaseAsset(
                    name=name,
                    url=url,
                    size_in_bytes=size_in_bytes,
                    api_client=self,
                )
            )

        return asset_locators

    def download_asset(self, url: str, download_path: str) -> bool:
        """Download the assets of the release that match the pattern (if specified).

        Parameters
        ----------
        url : dict
            The release URL.
        download_path : str
            The path to download assets.

        Returns
        -------
        bool
            Returns True if successful and False otherwise.
        """
        logger.debug("Download assets from %s at %s.", url, download_path)

        # Allow downloading binaries.
        response = send_get_http_raw(
            url,
            {
                "Accept": "application/octet-stream",
                "Authorization": self.headers["Authorization"],
            },
            timeout=defaults.getint("downloads", "timeout", fallback=120),
        )
        if not response:
            logger.error("Could not download the asset.")
            return False

        try:
            with open(download_path, "wb") as asset_file:
                asset_file.write(response.content)
        except OSError as error:
            logger.error(error)
            return False

        return True


def get_default_gh_client(access_token: str) -> GhAPIClient:
    """Return a GhAPIClient instance with default values.

    Parameters
    ----------
    access_token : str
        The GitHub personal access token

    Returns
    -------
    GhAPIClient
    """
    # A default gh client profile doesn't need any queries.
    if access_token:
        return GhAPIClient(
            {
                "headers": {
                    "Accept": "application/vnd.github.mercy-preview+json",
                    "Authorization": f"token {access_token}",
                },
                "query": [],
            }
        )
    return GhAPIClient(
        {
            "headers": {"Accept": "application/vnd.github.mercy-preview+json"},
            "query": [],
        }
    )
