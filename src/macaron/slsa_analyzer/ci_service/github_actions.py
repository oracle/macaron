# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module analyzes GitHub Actions CI."""

import glob
import logging
import os
from collections.abc import Iterable
from datetime import datetime, timezone
from enum import Enum

from macaron.code_analyzer.call_graph import BaseNode, CallGraph
from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.parsers.actionparser import parse as parse_action
from macaron.parsers.bashparser import BashCommands, extract_bash_from_ci
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService
from macaron.slsa_analyzer.git_service.api_client import GhAPIClient, get_default_gh_client
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService
from macaron.slsa_analyzer.git_service.github import GitHub

logger: logging.Logger = logging.getLogger(__name__)


class GHWorkflowType(Enum):
    """This class is used for different GitHub Actions types."""

    NONE = "None"
    INTERNAL = "internal"  # Workflows declared in the repo.
    EXTERNAL = "external"  # Third-party workflows.
    REUSABLE = "reusable"  # Reusable workflows.


class GitHubNode(BaseNode):
    """This class is used to create a call graph node for GitHub Actions."""

    def __init__(
        self, name: str, node_type: GHWorkflowType, source_path: str, parsed_obj: dict, caller_path: str
    ) -> None:
        """Initialize instance.

        Parameters
        ----------
        name : str
            Name of the workflow (or URL for reusable and external workflows).
        node_type : GHWorkflowType
            The type of workflow.
        source_path : str
            The path of the workflow.
        parsed_obj : dict
            The parsed Actions workflow object.
        caller_path : str
            The path to the caller workflow.
        """
        super().__init__()
        self.name = name
        self.node_type: GHWorkflowType = node_type
        self.source_path = source_path
        self.parsed_obj = parsed_obj
        self.caller_path = caller_path

    def __str__(self) -> str:
        return f"GitHubNode({self.name},{self.node_type})"


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

    def build_call_graph_from_node(self, node: GitHubNode) -> None:
        """Analyze the GitHub Actions node to build the call graph.

        Parameters
        ----------
        node : GitHubNode
            The node for a single GitHub Actions workflow.
        """
        if not node:
            return

        for _, job in node.parsed_obj.get("Jobs", {}).items():
            # Add third-party workflows.
            steps = job.get("Steps") or []
            for step in steps:
                if step.get("Exec") and "Uses" in step.get("Exec"):
                    # TODO: change source_path for external workflows.
                    node.add_callee(
                        GitHubNode(
                            name=step["Exec"]["Uses"]["Value"],
                            node_type=GHWorkflowType.EXTERNAL,
                            source_path="",
                            parsed_obj={},
                            caller_path=node.source_path,
                        )
                    )

            # Add reusable workflows.
            reusable = job.get("WorkflowCall")
            if reusable:
                logger.debug("Found reusable workflow: %s.", reusable["Uses"]["Value"])
                # TODO: change source_path for reusable workflows.
                node.add_callee(
                    GitHubNode(
                        name=reusable["Uses"]["Value"],
                        node_type=GHWorkflowType.REUSABLE,
                        source_path="",
                        parsed_obj={},
                        caller_path=node.source_path,
                    )
                )

    def build_call_graph(self, repo_path: str, macaron_path: str = "") -> CallGraph:
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

        root = GitHubNode(name="", node_type=GHWorkflowType.NONE, source_path="", parsed_obj={}, caller_path="")
        gh_cg = CallGraph(root, repo_path)

        # Parse GitHub Actions workflows.
        files = self.get_workflows(repo_path)
        for workflow_path in files:
            logger.debug(
                "Parsing %s",
                workflow_path,
            )
            parsed_obj: dict = parse_action(workflow_path)
            if not parsed_obj:
                logger.error("Could not parse Actions at the target %s.", repo_path)
                continue

            # Add internal workflows.
            workflow_name = os.path.basename(workflow_path)
            callee = GitHubNode(
                name=workflow_name,
                node_type=GHWorkflowType.INTERNAL,
                source_path=self.api_client.get_relative_path_of_workflow(workflow_name),
                parsed_obj=parsed_obj,
                caller_path="",
            )
            root.add_callee(callee)
            self.build_call_graph_from_node(callee)

        return gh_cg

    def extract_all_bash(self, callgraph: CallGraph, macaron_path: str = "") -> Iterable[BashCommands]:
        """Extract the bash scripts triggered by the CI service from parsing the configurations.

        Parameters
        ----------
        callgraph : CallGraph
            The call graph for GitHub Actions.
        macaron_path : str
            Macaron's root path (optional).

        Yields
        ------
        BashCommands
            The parsed bash script commands.
        """
        if not macaron_path:
            macaron_path = global_config.macaron_path

        # Analyze GitHub Actions workflows.
        # TODO: analyze reusable and external workflows.
        for callee in callgraph.bfs():
            if callee.node_type == GHWorkflowType.INTERNAL:
                logger.debug(
                    "Parsing %s",
                    callee.source_path,
                )

                if not callee.parsed_obj:
                    logger.error("Could not parse Actions at the target %s.", callgraph.repo_path)
                    continue

                for _, job in callee.parsed_obj.get("Jobs", {}).items():
                    steps = job.get("Steps") or []
                    for step in steps:
                        if step.get("Exec") and "Run" in step.get("Exec"):
                            yield from extract_bash_from_ci(
                                step["Exec"]["Run"]["Value"],
                                ci_file=self.api_client.get_relative_path_of_workflow(callee.name),
                                ci_type="github_actions",
                                recursive=True,
                                repo_path=callgraph.repo_path,
                                working_dir=step["Exec"]["WorkingDirectory"] or "",
                            )

    def has_latest_run_passed(
        self, repo_full_name: str, branch_name: str, commit_sha: str, commit_date: str, workflow: str
    ) -> str:
        """Check if the latest run of ``workflow`` on commit ``commit_sha`` is passing.

        This method queries for the list of workflow runs only from GitHub API using the repository full name.
        It will first perform a search using ``branch_name`` and ``commit_date`` as filters.
        If that failed, it will perform the same search but without any filtering.

        Parameters
        ----------
        repo_full_name : str
            The target repo's full name.
        branch_name : str
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
        logger.info("Getting the latest workflow run of %s on commit %s", workflow, commit_sha)

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
            logger.error("Cannot find data of workflow %s.", workflow)
            return ""

        try:
            workflow_id = workflow_data["id"]
        except KeyError:
            logger.error("Cannot get unique ID of workflow %s.", workflow)
            return ""

        logger.info("The unique ID of workflow %s is %s", workflow, workflow_id)

        # Perform the search.
        logger.info("Perform the workflow runs search with filtering.")
        latest_run_data = self.search_for_workflow_run(
            workflow_id,
            commit_sha,
            repo_full_name,
            branch_name,
            commit_date,
        )

        if not latest_run_data:
            logger.info("Cannot find target workflow run with filtering.")
            logger.info("Perform the workflow runs search without any filtering instead.")
            latest_run_data = self.search_for_workflow_run(
                workflow_id,
                commit_sha,
                repo_full_name,
                "",
                "",
            )

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

    def search_for_workflow_run(
        self,
        workflow_id: str,
        commit_sha: str,
        full_name: str,
        branch_name: str = "",
        created_after: str = "",
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
        branch_name : str
            The branch name to filter out workflow runs.
        created_after : str
            Only look for workflow runs after this date (e.g. 2022-03-11T16:44:40Z).

        Returns
        -------
        dict
            The response data of the latest workflow run or an empty dict if error.
        """
        logger.info(
            "Search for workflow runs of %s with query params (branch=%s,created=%s)",
            workflow_id,
            branch_name,
            created_after,
        )

        # Get the first page of runs for this workflow.
        query_page = 1
        runs_data = self.api_client.get_workflow_runs(full_name, branch_name, created_after, query_page)

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
                runs_data = self.api_client.get_workflow_runs(full_name, branch_name, created_after, query_page)
            except KeyError:
                logger.error("Error while reading run data. Skipping ...")
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
