# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module analyzes GitHub Actions CI."""

from __future__ import annotations

import glob
import logging
import os
from datetime import datetime, timedelta, timezone

from macaron.code_analyzer.dataflow_analysis.analysis import analyse_github_workflow_file
from macaron.code_analyzer.dataflow_analysis.core import Node, NodeForest
from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.errors import GitHubActionsValueError, ParseError
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService
from macaron.slsa_analyzer.git_service.api_client import GhAPIClient, get_default_gh_client
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService
from macaron.slsa_analyzer.git_service.github import GitHub

logger: logging.Logger = logging.getLogger(__name__)


class GitHubActions(BaseCIService):
    """This class contains the spec of the GitHub Actions."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__(name="github_actions")
        self.personal_access_token = ""  # nosec B105
        self.api_client: GhAPIClient = get_default_gh_client("")
        self.query_page_threshold = 10
        self.max_items_num = 100
        self.entry_conf = [".github/workflows"]
        self.max_workflow_persist = 90
        self.third_party_configurations: list[str] = []

    def set_api_client(self) -> None:
        """Set the GitHub client using the personal access token."""
        self.personal_access_token = global_config.gh_token
        self.api_client = get_default_gh_client(global_config.gh_token)

    def load_defaults(self) -> None:
        """Load the default values from defaults.ini."""
        if "ci.github_actions" in defaults:
            setattr(  # noqa: B010
                self, "query_page_threshold", defaults.getint("ci.github_actions", "query_page_threshold", fallback=10)
            )
            setattr(  # noqa: B010
                self, "max_items_num", defaults.getint("ci.github_actions", "max_items_num", fallback=100)
            )
            setattr(  # noqa: B010
                self, "entry_conf", defaults.get_list("ci.github_actions", "entry_conf", fallback=[".github/workflows"])
            )
            setattr(  # noqa: B010
                self, "max_workflow_persist", defaults.getint("ci.github_actions", "max_workflow_persist", fallback=90)
            )
            setattr(  # noqa: B010
                self,
                "third_party_configurations",
                defaults.get_list("ci.github_actions", "third_party_configurations", fallback=[]),
            )

    def is_detected(self, repo_path: str, git_service: BaseGitService | None = None) -> bool:
        """Return True if this CI service is used in the target repo.

        Parameters
        ----------
        repo_path : str
            The path to the target repo.

        git_service : BaseGitService
            The Git service hosting the target repo.

        Returns
        -------
        bool
            True if this CI service is detected, else False.
        """
        if git_service and not isinstance(git_service, GitHub):
            return False

        # GitHub Actions need a special detection implementation.
        # We need to check if YAML files exist in the workflows dir.
        exists = False
        logger.debug("Checking config files of CI Service: %s", self.name)
        for conf in self.entry_conf:
            for ext in ("*.yml", "*.yaml"):
                if glob.glob(os.path.join(repo_path, conf, ext)):
                    exists = True
                    break
        if not exists:
            logger.debug("GitHub Actions does not exist in this repository.")
        return exists

    def get_workflows(self, repo_path: str) -> list:
        """Get all workflows in a repository.

        Parameters
        ----------
        repo_path : str
            The path to the repository.

        Returns
        -------
        list
            The list of workflow files in this repository.
        """
        if not self.is_detected(repo_path=repo_path):
            logger.debug("There are no GitHub Actions workflows.")
            return []

        workflow_files = []
        for conf in self.entry_conf:
            for ext in ("*.yml", "*.yaml"):
                workflows = glob.glob(os.path.join(repo_path, conf, ext))
                if workflows:
                    logger.debug("Found GitHub Actions workflows.")
                    workflow_files.extend(workflows)
        return workflow_files

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str | None, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        """Check if the latest run of ``workflow`` on commit ``commit_sha`` is passing.

        This method queries for the list of workflow runs only from GitHub API using the repository full name.
        It will first perform a search using ``branch_name`` and ``commit_date`` as filters.
        If that failed, it will perform the same search but without any filtering.

        Parameters
        ----------
        repo_full_name : str
            The target repo's full name.
        branch_name : str | None
            The target branch.
        commit_sha : str
            The commit sha of the target repo.
        commit_date : str
            The commit date of the target repo.
        workflow : str
            The name of the workflow file (e.g `build.yml`).

        Returns
        -------
        str
            The URL for the passing workflow run, or empty if no passing GitHub Action build workflow is found.
        """
        logger.debug("Getting the latest workflow run of %s on commit %s", workflow, commit_sha)

        # Checking if the commit was created more than max_workflow_persist days ago.
        # We only avoid looking for workflow runs if only it's confirmed that the commit
        # is over max_workflow_persist days ago.
        # When there are errors or the commit is found out to be newer than current date,
        # we still look for workflow runs normally.
        try:
            # Setting the timezone to UTC because the date format.
            # We are using for GitHub Actions is in ISO format, which contains the offset
            # from the UTC timezone. For example: 2022-04-10T14:10:01+07:00
            current_time = datetime.now(timezone.utc)
            # TODO: it is safer to get commit_date as a datetime object directly.
            commit_date_obj = datetime.fromisoformat(commit_date)
            day_delta = (current_time - commit_date_obj).days

            if day_delta > self.max_workflow_persist:
                logger.info(
                    "The workflow run for commit %s was removed as it was created over %s days ago.",
                    commit_sha,
                    self.max_workflow_persist,
                )
                return ""
        except (OverflowError, ValueError) as error:
            logger.debug("Error while calculating the delta time of commit date: %s.", error)

        workflow_data = self.api_client.get_repo_workflow_data(repo_full_name, workflow)
        if not workflow_data:
            logger.debug("Cannot find data of workflow %s.", workflow)
            return ""

        try:
            workflow_id = workflow_data["id"]
        except KeyError:
            logger.debug("Cannot get unique ID of workflow %s.", workflow)
            return ""

        logger.info("The unique ID of workflow %s is %s", workflow, workflow_id)

        # Perform the search.
        logger.info("Perform the workflow runs search with filtering.")
        latest_run_data = self.search_for_workflow_run(
            workflow_id,
            commit_sha,
            repo_full_name,
            branch_name=branch_name,
            created_after=commit_date,
        )

        if not latest_run_data:
            logger.info("Cannot find target workflow run with filtering.")
            logger.info("Perform the workflow runs search without any filtering instead.")
            latest_run_data = self.search_for_workflow_run(workflow_id, commit_sha, repo_full_name)

        if not latest_run_data:
            logger.info("Cannot find target workflow run after trying both search methods.")
            return ""

        logger.info("**********")
        logger.info("Checking workflow run of %s.", workflow)

        # Skip this workflow when it's failing.
        try:
            run_id: str = latest_run_data["id"]
            html_url: str = latest_run_data["html_url"]
            if latest_run_data["conclusion"] != "success":
                logger.info("The workflow run for %s was unsuccessful. Skipping ....", workflow)
                return ""

            logger.info(
                "The workflow run of %s (id = %s, url = %s) is successful",
                workflow,
                run_id,
                html_url,
            )

            return html_url
        except KeyError as key_error:
            logger.info(
                "Cannot read data of %s from the GitHub API result. Error: %s",
                workflow,
                str(key_error),
            )

        return ""

    def check_publish_start_commit_timestamps(
        self, started_at: datetime, publish_date_time: datetime, commit_date_time: datetime, time_range: int
    ) -> bool:
        """
        Check if the timestamps of CI run, artifact publishing, and commit date are within the acceptable time range and valid.

        This function checks that the CI run has happened before the artifact publishing timestamp.

        This function also verifies whether the commit date is within an acceptable time range
        from the publish start time. The acceptable range is defined as half of the provided
        time range parameter.

        Parameters
        ----------
        started_at : datetime
            The timestamp indicating when the GitHub Actions workflow started.
        publish_date_time : datetime
            The timestamp indicating when the artifact is published.
        commit_date_time : datetime
            The timestamp of the source code commit.
        time_range : int
            The total acceptable time range in seconds.

        Returns
        -------
        bool
            True if the commit date is within the acceptable range from the publish start time,
                False otherwise. Returns False in case of any errors during timestamp comparisons.
        """
        # Make sure the source-code commit date is also within acceptable range.
        acceptable_range = time_range / 2
        try:
            if started_at < publish_date_time:
                if timedelta.total_seconds(abs(started_at - commit_date_time)) > acceptable_range:
                    logger.debug(
                        (
                            "The difference between GitHub Actions starting time %s and source commit time %s"
                            " is not within %s seconds."
                        ),
                        started_at,
                        commit_date_time,
                        acceptable_range,
                    )
                    return False
                return True

        except (ValueError, OverflowError, TypeError) as error:
            logger.debug(error)

        return False

    def workflow_run_in_date_time_range(
        self,
        repo_full_name: str,
        workflow: str,
        publish_date_time: datetime,
        commit_date_time: datetime,
        job_id: str,
        step_name: str | None,
        step_id: str | None,
        time_range: int = 0,
        callee_node_type: str | None = None,
    ) -> set[str]:
        """Check if the repository has a workflow run started before the date_time timestamp within the time_range.

        - This method queries the list of workflow runs using the GitHub API for the provided repository full name.
        - It will filter out the runs that are not triggered by the given workflow.
        - It will only accept the runs that from `date_time - time_range` to `date_time`.
        - If a `step_name` is provided, checks that it has started before the `date_time` and has succeeded.

        Parameters
        ----------
        repo_full_name : str
            The target repo's full name.
        workflow : str
            The workflow URL.
        date_time: datetime
            The datetime object to query.
        step_name: str | None
            The name of the step in the GitHub Action workflow that needs to be checked.
        step_id: str | None
            The ID of the step in the GitHub Action workflow that needs to be checked.
        time_range: int
            The date-time range in seconds. The default value is 0.

        Returns
        -------
        set[str]
            The set of URLs found for the workflow within the time range.

        Raises
        ------
        GitHubActionsValueError
            This error is raised when the GitHub Action workflow run misses values.
        """
        logger.debug(
            "Getting the latest workflow run of %s at publishing time %s and source commit date %s within time range %s.",
            workflow,
            str(publish_date_time),
            str(commit_date_time),
            str(time_range),
        )

        html_urls: set[str] = set()
        try:
            datetime_from = publish_date_time - timedelta(seconds=time_range)
        except (OverflowError, OSError, TypeError) as error:
            logger.debug(error)
            return html_urls

        # Perform the search.
        logger.debug("Search for the workflow runs within the range.")
        try:
            run_data = self.api_client.get_workflow_run_for_date_time_range(
                repo_full_name, f"{datetime_from.isoformat()}..{publish_date_time.isoformat()}"
            )
        except ValueError as error:
            logger.debug(error)
            return html_urls

        if not run_data:
            logger.debug("Unable to find any run data for the workflow %s", workflow)
            return html_urls

        logger.debug("Checking workflow run of %s.", workflow)
        try:
            # iterate through the responses in reversed order to add the run
            # closest to the `date_time - time_range` timestamp first.
            for item in reversed(run_data["workflow_runs"]):
                # The workflow parameter contains the URL to the workflow.
                # So we need to check that item["path"] is a substring of it.
                if item["path"] in workflow:
                    run_jobs = self.api_client.get_workflow_run_jobs(repo_full_name, item["id"])
                    if not run_jobs:
                        continue

                    # Find the matching step and check its `conclusion` and `started_at` attributes.
                    html_url = None
                    if not run_jobs["jobs"]:
                        raise GitHubActionsValueError("GitHub Actions workflow run misses jobs information.")
                    for job in run_jobs["jobs"]:
                        # If the deploy step is a Reusable Workflow, there won't be any steps in the caller job.
                        if callee_node_type == "reusable":
                            if not job["name"].startswith(job_id) or job["conclusion"] != "success":
                                continue
                            started_at = datetime.fromisoformat(job["started_at"])
                            if self.check_publish_start_commit_timestamps(
                                started_at=started_at,
                                publish_date_time=publish_date_time,
                                commit_date_time=commit_date_time,
                                time_range=time_range,
                            ):
                                run_id = item["id"]
                                html_url = item["html_url"]
                                break

                        if not job["steps"]:
                            raise GitHubActionsValueError(
                                f"GitHub Actions workflow run misses steps information for the {job_id} job ID."
                            )

                        for step in job["steps"]:
                            if step["name"] not in [step_name, step_id] or step["conclusion"] != "success":
                                continue
                            started_at = datetime.fromisoformat(step["started_at"])
                            if self.check_publish_start_commit_timestamps(
                                started_at=started_at,
                                publish_date_time=publish_date_time,
                                commit_date_time=commit_date_time,
                                time_range=time_range,
                            ):
                                run_id = item["id"]
                                html_url = item["html_url"]
                                logger.info(
                                    "The workflow run status of %s (id = %s, url = %s, step = %s) is %s.",
                                    workflow,
                                    run_id,
                                    html_url,
                                    step["name"],
                                    step["conclusion"],
                                )
                                break

                    if html_url:
                        html_urls.add(html_url)

        except KeyError as key_error:
            logger.debug(
                "Unable to read data of %s from the GitHub API result. Error: %s",
                workflow,
                str(key_error),
            )

        return html_urls

    def workflow_run_deleted(self, timestamp: datetime) -> bool:
        """
        Check if the CI run data is deleted based on a retention policy.

        Parameters
        ----------
        timestamp: datetime
            The timestamp of the CI run.

        Returns
        -------
        bool
            True if the CI run data is deleted.
        """
        # Setting the timezone to UTC because the date format
        # we are using for GitHub Actions is in ISO format, which contains the offset
        # from the UTC timezone. For example: 2022-04-10T14:10:01+07:00
        # GitHub retains GitHub Actions pipeline data for 400 days. So, we cannot analyze the
        # pipelines if artifacts are older than 400 days.
        # https://docs.github.com/en/rest/guides/using-the-rest-api-to-interact-with-checks?
        # apiVersion=2022-11-28#retention-of-checks-data
        # TODO: change this check if this issue is resolved:
        # https://github.com/orgs/community/discussions/138249
        if datetime.now(timezone.utc) - timedelta(days=400) > timestamp:
            logger.debug("Artifact published at %s is older than 400 days.", timestamp)
            return True

        return False

    def search_for_workflow_run(
        self,
        workflow_id: str,
        commit_sha: str,
        full_name: str,
        branch_name: str | None = None,
        created_after: str | None = None,
    ) -> dict:
        """Search for the target workflow run using GitHub API.

        This method will perform a query to get workflow runs. It will
        then look through each run data to determine the target workflow run.
        It will only stop if:

        - There are no results left
        - It reaches the maximum number of results (1000) allowed by GitHub API
        - It finds the workflow run we are looking for

        Parameters
        ----------
        workflow_id : str
            The unique id of the workflow file obtained through GitHub API.
        commit_sha : str
            The digest of the commit the workflow run on.
        full_name : str
            The full name of the repository (e.g. ``owner/repo``).
        branch_name : str | None
            The branch name to filter out workflow runs.
        created_after : str | None
            Only look for workflow runs after this date (e.g. 2022-03-11T16:44:40Z).

        Returns
        -------
        dict
            The response data of the latest workflow run or an empty dict if error.
        """
        logger.debug(
            "Search for workflow runs of %s with query params (branch=%s,created=%s)",
            workflow_id,
            branch_name,
            created_after,
        )

        # Get the first page of runs for this workflow.
        query_page = 1
        runs_data = self.api_client.get_workflow_runs(
            full_name, branch_name=branch_name, created_after=created_after, page=query_page
        )

        while runs_data and query_page <= self.query_page_threshold:
            logger.info(
                "Looking through runs data of %s in result page %s.",
                workflow_id,
                query_page,
            )
            try:
                for run in runs_data["workflow_runs"]:
                    if run["workflow_id"] == workflow_id and run["head_sha"] == commit_sha:
                        logger.info("Found workflow run of %s in page %s.", workflow_id, query_page)
                        return dict(run)

                logger.info("Didn't find any target run of %s on page %s.", workflow_id, query_page)
                if len(runs_data["workflow_runs"]) < self.max_items_num:
                    logger.info("No more workflow runs left to query.")
                    break

                # Query more items on the next result page of GitHub API.
                query_page += 1
                runs_data = self.api_client.get_workflow_runs(
                    full_name, branch_name=branch_name, created_after=created_after, page=query_page
                )
            except KeyError:
                logger.debug("Error while reading run data. Skipping ...")
                continue

        return {}

    def has_kws_in_log(self, latest_run: dict, build_log: list) -> bool:
        """Check the build log of this workflow run to see if it has build keywords.

        Parameters
        ----------
        latest_run : dict
            The latest run data from GitHub API.
        build_log : list
            The list of kws used to analyze the build log.

        Returns
        -------
        bool
            Whether the build log has build kw in it.
        """
        logger.info("Checking build log")
        jobs_data = self.api_client.get(latest_run["jobs_url"])

        for job in jobs_data["jobs"]:
            job_url = job["url"]
            log_url = f"{job_url}/logs"

            log_content = self.api_client.get_job_build_log(log_url)
            for keyword in build_log:
                if keyword in log_content:
                    logger.info('Found build kw "%s" in build log %s', keyword, log_url)
                    return True

        logger.info("No build kw in log file. Continue ...")
        return False

    def build_call_graph(self, repo_path: str, macaron_path: str = "") -> NodeForest:
        """Build the call Graph for GitHub Actions workflows.

        At the moment it does not analyze third-party workflows to include their callees.

        Parameters
        ----------
        repo_path : str
            The path to the repo.
        macaron_path: str
            Macaron's root path (optional).

        Returns
        -------
        CallGraph: CallGraph
            The call graph built for GitHub Actions.
        """
        if not macaron_path:
            macaron_path = global_config.macaron_path

        # Parse GitHub Actions workflows.
        files = self.get_workflows(repo_path)
        nodes: list[Node] = []
        for workflow_path in files:
            try:
                workflow_node = analyse_github_workflow_file(workflow_path, repo_path)

            except ParseError:
                logger.debug("Skip adding workflow at %s to the callgraph.", workflow_path)
                continue
            nodes.append(workflow_node)
        return NodeForest(nodes)

    def get_third_party_configurations(self) -> list[str]:
        """Get the list of third-party CI configuration files.

        Returns
        -------
        list[str]
            The list of third-party CI configuration files
        """
        return self.third_party_configurations
