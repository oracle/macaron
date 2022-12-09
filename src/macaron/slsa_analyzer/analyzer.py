# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module handles the cloning and analyzing a Git repo."""

import logging
import os
import subprocess  # nosec B404
import sys
from datetime import datetime

from git import InvalidGitRepositoryError
from pydriller.git import Git

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.config.target_config import Configuration
from macaron.database.database_manager import DatabaseManager
from macaron.dependency_analyzer import CycloneDxMaven, DependencyAnalyzer, DependencyInfo, DependencyTools
from macaron.output_reporter.reporter import FileReporter
from macaron.output_reporter.results import Record, Report, SCMStatus
from macaron.policy_engine.policy import Policy
from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool import BUILD_TOOLS
from macaron.slsa_analyzer.build_tool.maven import Maven

# To load all checks into the registry
from macaron.slsa_analyzer.checks import *  # pylint: disable=wildcard-import,unused-wildcard-import
from macaron.slsa_analyzer.checks.check_result import CheckResult, SkippedInfo
from macaron.slsa_analyzer.ci_service import CI_SERVICES
from macaron.slsa_analyzer.git_service import GIT_SERVICES, BaseGitService
from macaron.slsa_analyzer.git_service.base_git_service import NoneGitService
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from macaron.slsa_analyzer.specs.inferred_provenance import Provenance

logger: logging.Logger = logging.getLogger(__name__)


class Analyzer:
    """This class is used to analyze SLSA levels of a Git repo.

    Parameters
    ----------
    output_path : str
        The path to the output directory.
    build_log_path : str
        The path to store the build logs.
    """

    GIT_REPOS_DIR = "git_repos"
    """The directory in the output dir to store all cloned repositories."""

    TABLE_NAME = "analyze_result"
    """The name of the SQLite table which stores the analyze results."""

    def __init__(self, output_path: str, build_log_path: str) -> None:
        if not os.path.isdir(output_path):
            logger.critical("%s is not a valid directory. Exiting ...", output_path)
            sys.exit(1)

        if not registry.prepare():
            logger.error("Cannot start the analysis. Exiting ...")
            sys.exit(1)

        self.output_path = output_path

        # Prepare the directory to store all the build logs in the
        # root output dir.
        self.build_log_path = build_log_path
        if not os.path.isdir(self.build_log_path):
            os.makedirs(self.build_log_path)

        database_path = os.path.join(output_path, defaults.get("database", "db_name", fallback="macaron.db"))
        self.db_man = DatabaseManager(database_path)

        # If provided with local_repos_path, we resolve the path of the target repo
        # to the path within local_repos_path.
        # If not, we use the default value <output_path>/git_repos/local_repos.
        self.local_repos_path = (
            global_config.local_repos_path
            if global_config.local_repos_path
            else os.path.join(global_config.output_path, Analyzer.GIT_REPOS_DIR, "local_repos")
        )
        if not os.path.exists(self.local_repos_path):
            os.makedirs(self.local_repos_path, exist_ok=True)

        # Get the policy from global config.
        self.policy: Policy | None = None
        if global_config.policy_path:
            self.policy = Policy.make_policy(global_config.policy_path)

        # Initialize the reporters to store analysis data to files.
        self.reporters: list[FileReporter] = []

    def run(self, user_config: dict, skip_deps: bool = False) -> int:
        """Run the analysis and write results to the output path.

        This method handles the configuration file and writes the result html reports including dependencies.
        The return status code of this method depends on the analyzing status of the main repo only.

        Parameters
        ----------
        user_config : dict
            The dictionary that contains the user config parsed from the yaml file.
        skip_deps : bool
            Flag to skip dependency resolution.

        Returns
        -------
        int
            The return status code.
        """
        main_config = Configuration(user_config.get("target", {}))
        deps_config: list[Configuration] = [Configuration(dep) for dep in user_config.get("dependencies", [])]
        deps_resolved: dict[str, DependencyInfo] = {}

        # Analyze the main target.
        main_record = self.run_single(main_config)

        # Write the results of main target to DB.
        if main_record.status != SCMStatus.AVAILABLE or not main_record.context:
            logger.info("Analysis has failed.")
            return 1

        # Run the chosen dependency analyzer plugin.
        if skip_deps:
            logger.info("Skipping automatic dependency analysis...")
        else:
            deps_resolved = self.resolve_dependencies(main_record.context)

        # Merge the automatically resolved dependencies with the manual configuration.
        deps_config = DependencyAnalyzer.merge_configs(deps_config, deps_resolved)

        # Create a report instance with the record of the main repo.
        report = Report(main_record)

        duplicated_scm_records: list[Record] = []

        if deps_config:
            logger.info("Start analyzing the dependencies.")
            for config in deps_config:
                dep_status: SCMStatus = config.get_value("available")
                if dep_status != SCMStatus.AVAILABLE:
                    dep_record: Record = Record(
                        record_id=config.get_value("id"),
                        description=config.get_value("note"),
                        pre_config=config,
                        status=config.get_value("available"),
                    )
                    report.add_dep_record(dep_record)
                    if dep_status == SCMStatus.DUPLICATED_SCM:
                        duplicated_scm_records.append(dep_record)

                    continue
                dep_record = self.run_single(config, report.record_mapping)
                report.add_dep_record(dep_record)
        else:
            logger.info("Found no dependencies to analyze.")

        # Populate the record of duplicated scm dependencies with the
        # context of analyzed dependencies if available.
        for dup_record in duplicated_scm_records:
            find_ctx = report.find_ctx(dup_record.pre_config.get_value("path"))
            dup_record.context = find_ctx

        # Store the analysis result into the SQLite database.
        for ctx in report.get_ctxs():
            self.store_result_to_db(ctx)

        # Store the analysis result into report files.
        self.generate_reports(report)

        # Print the analysis result into the console output.
        logger.info(str(report))

        logger.info("Analysis Completed!")
        return 0

    def generate_reports(self, report: Report) -> None:
        """Generate the report of the analysis to all registered reporters.

        Parameters
        ----------
        report : Report
            The report of the analysis.
        """
        if not report.root_record.context:
            logger.critical("The main repository analysis failed. Cannot generate a report for it.")
            return

        output_target_path = os.path.join(
            global_config.output_path, "reports", git_url.get_repo_dir_name(report.root_record.context.remote_path)
        )
        os.makedirs(output_target_path, exist_ok=True)

        for reporter in self.reporters:
            reporter.generate(output_target_path, report)

    def resolve_dependencies(self, main_ctx: AnalyzeContext) -> dict[str, DependencyInfo]:
        """Resolve the dependencies of the main target repo.

        Parameters
        ----------
        main_ctx : AnalyzeContext
            The context of object of the target repository.

        Returns
        -------
        dict[str, DependencyInfo]
            A dictionary where artifacts are grouped based on ``artifactId:groupId``.
        """
        deps_resolved = {}

        if "dependency.resolver" not in defaults or "dep_tool_maven" not in defaults["dependency.resolver"]:
            logger.info("No default dependency analyzer is found. Skipping automatic dependency analysis...")
        elif not DependencyAnalyzer.tool_valid(
            defaults.get("dependency.resolver", "dep_tool_maven", fallback="cyclonedx-maven:2.6.2")
        ):
            logger.info(
                "Dependency analyzer %s is not valid. Skipping automatic dependency analysis...",
                defaults.get(
                    "dependency.resolver",
                    "dep_tool_maven",
                    fallback="cyclonedx-maven:2.6.2",
                ),
            )
        else:
            try:
                # Load the default values for the dependency analyzer tool.
                # TODO: add support for Gradle dependency resolvers.
                tool_name, tool_version = tuple(
                    defaults.get(
                        "dependency.resolver",
                        "dep_tool_maven",
                        fallback="cyclonedx-maven:2.6.2",
                    ).split(":")
                )
                if tool_name == DependencyTools.CYCLONEDX_MAVEN:
                    dep_analyzer = CycloneDxMaven(  # type: ignore
                        resources_path=global_config.resources_path,
                        file_name="bom.json",
                        debug_path=os.path.join(self.output_path, "cdx_debug.json"),
                        tool_version=tool_version,
                    )

                # The repo path can be pointed to the same directory as the macaron root path.
                # However, there shouldn't be any pom.xml in the macaron root path.
                if not os.path.isfile(os.path.join(global_config.macaron_path, "pom.xml")):
                    if isinstance(main_ctx.dynamic_data["build_spec"]["tool"], Maven):
                        logger.info(
                            "Running %s version %s dependency analyzer on %s",
                            tool_name,
                            tool_version,
                            main_ctx.repo_path,
                        )

                        log_path = os.path.join(
                            global_config.build_log_path,
                            f"{main_ctx.repo_name}.{tool_name}.log",
                        )

                        commands = dep_analyzer.get_cmd()
                        # We are using this flag because we are running
                        # mvnw in the macaron root path, not in the target repo directory.
                        commands.extend(["-f", main_ctx.repo_path])
                        # Suppressing Bandit's B603 report because the repo paths are validated.
                        analyzer_output = subprocess.run(  # nosec B603
                            commands,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            check=True,
                            cwd=global_config.resources_path,
                            timeout=defaults.getint("dependency.resolver", "timeout", fallback=1200),
                        )
                        with open(log_path, mode="w", encoding="utf-8") as log_file:
                            logger.info("Storing dependency resolver log to %s", log_path)
                            log_file.write(analyzer_output.stdout.decode("utf-8"))

                        deps_resolved = dep_analyzer.collect_dependencies(main_ctx.repo_path)
                    else:
                        logger.info(
                            "Dependency analyzer is not available for %s",
                            main_ctx.dynamic_data["build_spec"]["tool"].name,
                        )
                else:
                    logger.error(
                        "Please remove pom.xml file in %s.",
                        global_config.macaron_path,
                    )

            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                logger.error(error)
                with open(log_path, mode="w", encoding="utf-8") as log_file:
                    logger.info("Storing dependency resolver log to %s", log_path)
                    log_file.write(error.output.decode("utf-8"))
            except FileNotFoundError as error:
                # Only happen if the gradlew at the repo dir has an invalid format
                logger.error(error)

        return deps_resolved

    def run_single(self, config: Configuration, existing_records: dict[str, Record] = None) -> Record:
        """Run the checks for a single repository target.

        Please use Analyzer.run if you want to run the analysis for a config parsed from
        user provided yaml file.

        Parameters
        ----------
        config : str
            The configuration for running Macaron.

        existing_records : dict[str, Record]
            The mapping of existing records that the analysis has run successfully.

        Returns
        -------
        Record
            The record of the analysis for this repository.
        """
        repo_id = config.get_value("id")
        repo_path = config.get_value("path")
        req_branch = config.get_value("branch")
        req_digest = config.get_value("digest")

        logger.info("=====================================")
        logger.info("Analyzing %s", repo_id)
        logger.info("Repo path: %s", repo_path)
        logger.info("=====================================")

        git_obj = self._prepare_repo(
            os.path.join(self.output_path, self.GIT_REPOS_DIR),
            repo_path,
            req_branch,
            req_digest,
        )
        if not git_obj:
            error_msg = "Cannot prepare the repository for analysis."
            logger.error(error_msg)
            return Record(
                record_id=repo_id,
                description=error_msg,
                pre_config=config,
                status=SCMStatus.ANALYSIS_FAILED,
            )

        # TODO: use both the repo URL and the commit hash to check.
        if existing_records and git_url.get_remote_url_of_local_repo(git_obj) in existing_records:
            info_msg = "This repository has been already analyzed."
            logger.info(info_msg)
            return Record(
                record_id=repo_id,
                description=info_msg,
                pre_config=config,
                status=SCMStatus.DUPLICATED_SCM,
            )

        analyze_ctx = self.get_analyze_ctx(req_branch, git_obj)
        analyze_ctx.check_results = self.perform_checks(analyze_ctx)

        return Record(
            record_id=repo_id,
            description="Analysis Completed.",
            pre_config=config,
            status=SCMStatus.AVAILABLE,
            context=analyze_ctx,
        )

    def get_analyze_ctx(self, branch_name: str, git_obj: Git) -> AnalyzeContext:
        """Return the analyze context for a target repository.

        Parameters
        ----------
        git_obj : Git
            The pydriller Git object of the target repository.
        branch_name : str
            The name of the branch that we are analyzing.
            We need this because when the target repository is in a detached state,
            the current branch name cannot be determined.

        Returns
        -------
        AnalyzeContext
            The context of object of the target repository.
        """
        remote_path = git_url.get_remote_url_of_local_repo(git_obj)
        full_name = git_url.get_repo_full_name_from_url(remote_path)
        logger.info("The full name of this repository is %s", full_name)

        res_branch = ""

        if branch_name:
            res_branch = branch_name
        else:
            try:
                res_branch = git_obj.repo.active_branch.name
            except TypeError as err:
                # HEAD is a detached symbolic reference. This happens when we checkout a commit.
                # However, it shouldn't happen as we don't allow specifying a commit digest without
                # a branch in the config.
                logger.critical("The HEAD of the repo does not point to any branch.")
                logger.error(err)
                res_branch = ""

        # Get the head commit.
        # This is the commit that Macaron will run the analysis on.
        head_commit = git_obj.get_head()
        commit_sha = head_commit.hash

        # TODO: add commit_date to AnalyzeContext as a property.
        # Each CI service should handle the datetime object accordingly.
        commit_date: datetime = head_commit.committer_date

        # GitHub API uses the ISO format datetime string.
        commit_date_str = commit_date.isoformat(sep="T", timespec="seconds")

        logger.info(
            "Running the analysis on branch %s, commit_sha %s, commit_date: %s",
            res_branch,
            commit_sha,
            commit_date_str,
        )

        # Initialize the analyzing context for this repository.
        analyze_ctx = AnalyzeContext(
            full_name,
            str(git_obj.path),
            git_obj,
            res_branch,
            commit_sha,
            commit_date_str,
            global_config.macaron_path,
            self.output_path,
            remote_path,
        )

        return analyze_ctx

    def _prepare_repo(
        self,
        target_dir: str,
        repo_path: str,
        branch_name: str = "",
        digest: str = "",
    ) -> Git:
        """Prepare the target repository for analysis.

        If ``repo_path`` is a remote path, the target repo is cloned to ``{target_dir}/{unique_path}``.
        The ``unique_path`` of a repository will depend on its remote url.
        For example, if given the ``repo_path`` https://github.com/org/name.git, it will
        be cloned to ``{target_dir}/github_com/org/name``.

        If ``repo_path`` is a local path, this method will check if ``repo_path`` resolves to a directory inside
        ``Analyzer.local_repos_path`` and to a valid git repository.

        Parameters
        ----------
        target_dir : str
            The directory where all remote repository will be cloned.
        repo_path: str
            The path to the repository, can be either local or remote.
        branch_name: str
            The name of the branch we want to checkout.
        digest: str
            The hash of the commit that we want to checkout in the branch.

        Returns
        -------
        Git
            The pydriller.Git object of the repository or None if error.
        """
        # Cannot specify a commit hash without specifying the branch.
        if not branch_name and digest:
            logger.error(
                "Cannot specify a commit hash without specifying the branch for repo at %s.",
                repo_path,
            )
            return None

        logger.info(
            "Preparing the repository for the analysis (path=%s, branch=%s, digest=%s)",
            repo_path,
            branch_name,
            digest,
        )

        resolved_local_path = ""

        if git_url.is_remote_repo(repo_path):
            logger.info("The path to repo %s is a remote path.", repo_path)
            resolved_remote_path = git_url.get_remote_vcs_url(repo_path)
            if not resolved_remote_path:
                logger.error("The provided path to repo %s is not a valid remote path.", repo_path)
                return None

            git_service = self.get_git_service(resolved_remote_path)
            if not git_service.can_clone_remote_repo(resolved_remote_path):
                logger.error("Cannot clone the remote repo at %s", resolved_remote_path)
                return None

            repo_unique_path = git_url.get_repo_dir_name(resolved_remote_path)
            resolved_local_path = os.path.join(target_dir, repo_unique_path)
            git_url.clone_remote_repo(resolved_local_path, resolved_remote_path)
        else:
            logger.info("The path to repo %s is a local path.", repo_path)
            resolved_local_path = self._resolve_local_path(self.local_repos_path, repo_path)

        if resolved_local_path:
            try:
                git_obj = Git(resolved_local_path)
            except InvalidGitRepositoryError:
                logger.error("No git repo exists at %s.", resolved_local_path)
                return None
        else:
            logger.error("Error happened while preparing the repo.")
            return None

        if git_url.is_empty_repo(git_obj):
            logger.error("The target repository does not have any commit.")
            return None

        if not git_url.reset_git_repo(git_obj):
            logger.error("Cannot reset the target repository.")
            return None

        if not git_url.check_out_repo_target(git_obj, branch_name, digest):
            logger.error("Cannot checkout the specific branch or commit of the target repo.")
            return None

        return git_obj

    @staticmethod
    def get_git_service(remote_path: str) -> BaseGitService:
        """Return the git service used from the remote path.

        Parameters
        ----------
        remote_path : str
            The remote path of the repo.

        Returns
        -------
        BaseGitService
            The git service derived from the remote path.
        """
        for git_service in GIT_SERVICES:
            git_service.load_defaults()
            if git_service.is_detected(remote_path):
                return git_service

        return NoneGitService()

    @staticmethod
    def _resolve_local_path(start_dir: str, local_path: str) -> str:
        """Resolve the local path and check if it's within a directory.

        This method returns an empty string if there are errors with resolving ``local_path``
        (e.g. non-existed dir, broken symlinks, etc.) or ``start_dir`` does not exist.

        Parameters
        ----------
        start_dir : str
            The directory to look for the existence of path.
        local_path: str
            The local path to resolve within start_dir.

        Returns
        -------
        str
            The resolved path in canonical form or an empty string if errors.
        """
        # Resolve the path by joining dir and path.
        # Because strict mode is enabled, if a path doesn’t exist or a symlink loop
        # is encountered, OSError is raised.
        # ValueError is raised if we use both relative and absolute paths in os.path.commonpath.
        try:
            dir_real = os.path.realpath(start_dir, strict=True)
            resolve_path = os.path.realpath(os.path.join(start_dir, local_path), strict=True)
            if os.path.commonpath([resolve_path, dir_real]) != dir_real:
                return ""

            return resolve_path
        except (OSError, ValueError) as error:
            logger.error(error)
            return ""

    def perform_checks(self, analyze_ctx: AnalyzeContext) -> dict[str, CheckResult]:
        """Run the analysis on the target repo and return the results.

        Parameters
        ----------
        analyze_ctx : AnalyzeContext
            The object containing processed data for the target repo.

        Returns
        -------
        dict[str, CheckResult]
            The mapping between the check id and its result.
        """
        # Determine the git service.
        git_service = self.get_git_service(analyze_ctx.remote_path)
        if isinstance(git_service, NoneGitService):
            logger.error("Unsupported git service for %s", analyze_ctx.repo_full_name)
        else:
            logger.info("Detect git service %s for %s.", git_service.name, analyze_ctx.repo_full_name)
            analyze_ctx.dynamic_data["git_service"] = git_service

        # Determine the build tool.
        for build_tool in BUILD_TOOLS:
            build_tool.load_defaults()
            logger.info(
                "Checking if the repo %s uses build tool %s",
                analyze_ctx.repo_full_name,
                build_tool.name,
            )

            if build_tool.is_detected(analyze_ctx.git_obj.path):
                logger.info("The repo uses %s build tool.", build_tool.name)
                analyze_ctx.dynamic_data["build_spec"]["tool"] = build_tool
                break

        if not analyze_ctx.dynamic_data["build_spec"].get("tool"):
            logger.info(
                "Cannot discover any build tool for %s or the build tool is not supported.",
                analyze_ctx.repo_full_name,
            )

        # Determine the CI services.
        for ci_service in CI_SERVICES:
            ci_service.load_defaults()
            ci_service.set_api_client()

            if ci_service.is_detected(analyze_ctx.git_obj.path):
                logger.info("The repo uses %s CI service.", ci_service.name)

                # Parse configuration files and generate IRs.
                # Add the bash commands to the context object to be used by other checks.
                callgraph = ci_service.build_call_graph(
                    analyze_ctx.repo_path, os.path.relpath(analyze_ctx.repo_path, analyze_ctx.output_dir)
                )
                bash_commands = list(ci_service.extract_all_bash(callgraph)) if callgraph else []
                analyze_ctx.dynamic_data["ci_services"].append(
                    CIInfo(
                        service=ci_service,
                        bash_commands=bash_commands,
                        callgraph=callgraph,
                        provenance_assets=[],
                        latest_release={},
                        provenances=[Provenance().payload],
                    )
                )

        # TODO: Get the list of skipped checks from user configuration
        skipped_checks: list[SkippedInfo] = []

        # Get the reference to the policy.
        analyze_ctx.dynamic_data["policy"] = self.policy

        results = registry.scan(analyze_ctx, skipped_checks)

        return results

    def store_result_to_db(self, analyze_ctx: AnalyzeContext) -> None:
        """Store the content of an analyzed context into the database.

        Parameters
        ----------
        analyze_ctx : AnalyzeContext
            The analyze context to store into the database.
        """
        logger.info(
            "Inserting result of %s to %s",
            analyze_ctx.repo_full_name,
            defaults.get("database", "db_name", fallback="macaron.db"),
        )
        if not self.db_man.is_init:
            self.init_database()
        insert_data = analyze_ctx.get_insert_data()
        insert_query = AnalyzeContext.gen_insert_analyze_result_query(Analyzer.TABLE_NAME)
        self.db_man.execute_insert_query(insert_query, insert_data)

    def init_database(self) -> None:
        """Initiate the database connection and create the table to store the analyze result."""
        self.db_man.init_conn()

        # Create the table for storing analyze result
        analyze_result_table = AnalyzeContext.gen_create_table_query(Analyzer.TABLE_NAME)
        self.db_man.execute_multi_queries(analyze_result_table)
