# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module handles the cloning and analyzing a Git repo."""

import logging
import os
import subprocess  # nosec B404
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
from urllib.parse import ParseResult, urlunparse

import sqlalchemy.exc
from git import InvalidGitRepositoryError
from packageurl import PackageURL
from pydriller.git import Git
from sqlalchemy.orm import Session

from macaron import __version__
from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.config.target_config import Configuration
from macaron.database.database_manager import DatabaseManager, get_db_manager, get_db_session
from macaron.database.table_definitions import Analysis, Component, Repository
from macaron.dependency_analyzer import (
    DependencyAnalyzer,
    DependencyAnalyzerError,
    DependencyInfo,
    NoneDependencyAnalyzer,
)
from macaron.dependency_analyzer.cyclonedx import get_deps_from_sbom
from macaron.errors import CloneError, DuplicateError, InvalidPURLError, PURLNotFoundError, RepoCheckOutError
from macaron.output_reporter.reporter import FileReporter
from macaron.output_reporter.results import Record, Report, SCMStatus
from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool import BUILD_TOOLS

# To load all checks into the registry
from macaron.slsa_analyzer.checks import *  # pylint: disable=wildcard-import,unused-wildcard-import # noqa: F401,F403
from macaron.slsa_analyzer.checks.check_result import CheckResult, SkippedInfo
from macaron.slsa_analyzer.ci_service import CI_SERVICES
from macaron.slsa_analyzer.database_store import store_analyze_context_to_db
from macaron.slsa_analyzer.git_service import GIT_SERVICES, BaseGitService
from macaron.slsa_analyzer.git_service.base_git_service import NoneGitService
from macaron.slsa_analyzer.package_registry import PACKAGE_REGISTRIES
from macaron.slsa_analyzer.provenance.expectations.expectation_registry import ExpectationRegistry
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from macaron.slsa_analyzer.specs.inferred_provenance import Provenance
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


class Analyzer:
    """This class is used to analyze SLSA levels of a Git repo."""

    GIT_REPOS_DIR = "git_repos"
    """The directory in the output dir to store all cloned repositories."""

    def __init__(self, output_path: str, build_log_path: str) -> None:
        """Initialize instance.

        Parameters
        ----------
        output_path : str
            The path to the output directory.
        build_log_path : str
            The path to store the build logs.
        """
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

        # Load the expectations from global config.
        self.expectations = ExpectationRegistry(global_config.expectation_paths)

        # Initialize the reporters to store analysis data to files.
        self.reporters: list[FileReporter] = []

        # Get the db manager singleton object.
        self.db_man: DatabaseManager = get_db_manager()

        # Create database tables: all checks have been registered so all tables should be mapped now
        self.db_man.create_tables()

    def run(self, user_config: dict, sbom_path: str = "", skip_deps: bool = False) -> int:
        """Run the analysis and write results to the output path.

        This method handles the configuration file and writes the result html reports including dependencies.
        The return status code of this method depends on the analyzing status of the main repo only.

        Parameters
        ----------
        user_config : dict
            The dictionary that contains the user config parsed from the yaml file.
        sbom_path : str
            The path to the SBOM.
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

        # Get a single session once for the whole analysis.
        # Note if anything goes wrong, we will not commit anything
        # to the database. So, atomicity is at analysis level.
        # TODO: change the atomicity level per component run to allow
        # parallelizing dependencies.
        try:
            with Session(self.db_man.engine) as session, session.begin():
                # Cache the singleton session object.
                db_session: Session = get_db_session(session)

                # Create a transient SQLAlchemy instance for Analysis.
                # Note that the changes will be committed to the DB when the
                # current Session context terminates.
                analysis = Analysis(
                    analysis_time=datetime.now(tz=timezone.utc),
                    macaron_version=__version__,
                )

                # Analyze the main target.
                main_record = self.run_single(main_config, analysis)

                if main_record.status != SCMStatus.AVAILABLE or not main_record.context:
                    logger.info("Analysis has failed.")
                    return os.EX_DATAERR

                # Run the chosen dependency analyzer plugin.
                if skip_deps:
                    logger.info("Skipping automatic dependency analysis...")
                elif sbom_path:
                    logger.info("Getting the dependencies from the SBOM defined at %s.", sbom_path)
                    deps_resolved = get_deps_from_sbom(sbom_path)
                else:
                    deps_resolved = self.resolve_dependencies(main_record.context) if main_record.context else {}

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
                        dep_record = self.run_single(config, analysis, report.record_mapping)
                        report.add_dep_record(dep_record)
                else:
                    logger.info("Found no dependencies to analyze.")

                # Populate the record of duplicated scm dependencies with the
                # context of analyzed dependencies if available.
                for dup_record in duplicated_scm_records:
                    find_ctx = report.find_ctx(dup_record.pre_config.get_value("id"))
                    dup_record.context = find_ctx

                for record in report.get_records():
                    if not record.status == SCMStatus.DUPLICATED_SCM:
                        if record.context:
                            store_analyze_context_to_db(record.context)

                # Store dependency relations.
                for parent, child in report.get_dependencies():
                    parent.component.dependencies.append(child.component)

                # Store the analysis result into report files.
                self.generate_reports(report)

                # Print the analysis result into the console output.
                logger.info(str(report))

                db_session.add(analysis)

                logger.info(
                    "The PURL string for the main target software component in this analysis is '%s'.",
                    main_record.context.component.purl,
                )
                logger.info("Analysis Completed!")
                return os.EX_OK
        except sqlalchemy.exc.SQLAlchemyError as error:
            logger.critical("Database error %s", error)
            logger.critical("The main repository analysis failed. Cannot generate a report for it.")
            return os.EX_DATAERR
        except RuntimeError as error:
            logger.critical(error)
            return os.EX_DATAERR

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
            global_config.output_path, "reports", report.root_record.context.component.report_dir_name
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
        deps_resolved: dict[str, DependencyInfo] = {}

        build_tools = main_ctx.dynamic_data["build_spec"]["tools"]
        if not build_tools:
            logger.info("Unable to find any valid build tools.")
            return {}

        # Grab dependencies for each build tool, collate all into the deps_resolved
        for build_tool in build_tools:
            try:
                dep_analyzer = build_tool.get_dep_analyzer(main_ctx.component.repository.fs_path)
            except DependencyAnalyzerError as error:
                logger.error("Unable to find a dependency analyzer for %s: %s", build_tool.name, error)
                return {}

            if isinstance(dep_analyzer, NoneDependencyAnalyzer):
                logger.info(
                    "Dependency analyzer is not available for %s",
                    build_tool.name,
                )
                return {}

            # Start resolving dependencies.
            logger.info(
                "Running %s version %s dependency analyzer on %s",
                dep_analyzer.tool_name,
                dep_analyzer.tool_version,
                main_ctx.component.repository.fs_path,
            )

            log_path = os.path.join(
                global_config.build_log_path,
                f"{main_ctx.component.report_file_name}.{dep_analyzer.tool_name}.log",
            )

            # Clean up existing SBOM files.
            dep_analyzer.remove_sboms(main_ctx.component.repository.fs_path)

            commands = dep_analyzer.get_cmd()
            working_dirs: Iterable[Path] = build_tool.get_build_dirs(main_ctx.component.repository.fs_path)
            for working_dir in working_dirs:
                # Get the absolute path to use as the working dir in the subprocess.
                working_dir = Path(main_ctx.component.repository.fs_path).joinpath(working_dir)

                try:
                    # Suppressing Bandit's B603 report because the repo paths are validated.
                    analyzer_output = subprocess.run(  # nosec B603
                        commands,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=True,
                        cwd=str(working_dir),
                        timeout=defaults.getint("dependency.resolver", "timeout", fallback=1200),
                    )
                    with open(log_path, mode="a", encoding="utf-8") as log_file:
                        log_file.write(analyzer_output.stdout.decode("utf-8"))

                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                    logger.error(error)
                    with open(log_path, mode="a", encoding="utf-8") as log_file:
                        log_file.write(error.output.decode("utf-8"))
                except FileNotFoundError as error:
                    logger.error(error)

                # We collect the generated SBOM as a best effort, even if the build exits with errors.
                # TODO: add improvements to help the SBOM build succeed as much as possible.
                # Update deps_resolved with new dependencies.
                deps_resolved |= dep_analyzer.collect_dependencies(str(working_dir))

            logger.info("Stored dependency resolver log for %s to %s.", dep_analyzer.tool_name, log_path)

        return deps_resolved

    def run_single(
        self,
        config: Configuration,
        analysis: Analysis,
        existing_records: dict[str, Record] | None = None,
    ) -> Record:
        """Run the checks for a single repository target.

        Please use Analyzer.run if you want to run the analysis for a config parsed from
        user provided yaml file.

        Parameters
        ----------
        config: Configuration
            The configuration for running Macaron.
        analysis: Analysis
            The current analysis instance.
        existing_records : dict[str, Record] | None
            The mapping of existing records that the analysis has run successfully.

        Returns
        -------
        Record
            The record of the analysis for this repository.
        """
        repo_id = config.get_value("id")
        component = None
        try:
            component = self.add_component(config, analysis, existing_records)
        except PURLNotFoundError as error:
            logger.error(error)
            return Record(
                record_id=repo_id,
                description=str(error),
                pre_config=config,
                status=SCMStatus.ANALYSIS_FAILED,
            )
        except DuplicateCmpError as error:
            logger.debug(error)
            return Record(
                record_id=repo_id,
                description=str(error),
                pre_config=config,
                status=SCMStatus.DUPLICATED_SCM,
                context=error.context,
            )

        logger.info("=====================================")
        logger.info("Analyzing %s", repo_id)
        logger.info("With PURL: %s", component.purl)
        logger.info("=====================================")

        analyze_ctx = self.get_analyze_ctx(component)
        analyze_ctx.dynamic_data["expectation"] = self.expectations.get_expectation_for_target(
            analyze_ctx.component.purl.split("@")[0]
        )
        analyze_ctx.check_results = self.perform_checks(analyze_ctx)

        return Record(
            record_id=repo_id,
            description="Analysis Completed.",
            pre_config=config,
            status=SCMStatus.AVAILABLE,
            context=analyze_ctx,
        )

    def add_repository(self, branch_name: str, git_obj: Git) -> Repository | None:
        """Create a repository instance for a target repository.

        The repository instances are transient objects for SQLAlchemy, which may be
        added to the database ultimately.

        Parameters
        ----------
        branch_name : str
            The name of the branch that we are analyzing.
            We need this because when the target repository is in a detached state,
            the current branch name cannot be determined.
        git_obj : Git
            The pydriller Git object of the target repository.

        Returns
        -------
        Repository | None
            The target repository or None if not found.
        """
        # We get the origin url from the git repository.
        # If it is a remote url, we could get the full name of the repository directly.
        # For example, https://github.com/oracle/macaron -> oracle/macaron.
        # However, if the origin url is a path to a local repository, we will assign a default
        # name for it (i.e local_repos/<basename_of_the_local_path>).
        # For example, /home/path/to/repo -> local_repos/repo.
        origin_remote_path = git_url.get_remote_origin_of_local_repo(git_obj)
        full_name = git_url.get_repo_full_name_from_url(origin_remote_path)
        complete_name = git_url.get_repo_complete_name_from_url(origin_remote_path)
        if not complete_name:
            complete_name = f"local_repos/{Path(origin_remote_path).name}"

        logger.info("The complete name of this repository is %s", complete_name)

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

        # We only allow complete_name's length to be 2 or 3 because we need to construct PURL
        # strings using the complete_name, i.e., type/namespace/name@commitsha
        if (parts_len := len(Path(complete_name).parts)) < 2 or parts_len > 3:
            logger.error("The repository path %s is not valid.", complete_name)
            return None

        repository = Repository(
            full_name=full_name,
            complete_name=complete_name,
            remote_path=origin_remote_path,
            branch_name=res_branch,
            commit_sha=commit_sha,
            commit_date=commit_date_str,
            fs_path=str(git_obj.path),
            files=git_obj.files(),
        )

        logger.info(
            "Running the analysis on branch %s, commit_sha %s, commit_date: %s",
            res_branch,
            commit_sha,
            commit_date_str,
        )

        return repository

    @staticmethod
    def to_domain_from_known_purl_types(purl_type: str) -> str | None:
        """Return the git service domain from a known purl type.

        This method is used to handle the cases where the purl type value is not the git domain but a pre-defined
        repo-based type in https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst.

        Note that this method will be updated when there are new pre-defined types as per the PURL specification.

        Parameters
        ----------
        purl_type : str
            The type field of the PURL.

        Returns
        -------
        str | None
            The git service domain corresponding to the purl type or None if the purl type is unknown.
        """
        known_types = {"github": "github.com", "bitbucket": "bitbucket.org"}
        return known_types.get(purl_type, None)

    @staticmethod
    def to_repo_path(purl: PackageURL, available_domains: list[str]) -> str | None:
        """Return the repository path from the PURL string.

        This method only supports converting a PURL with the following format:

            pkg:<type>/<namespace>/<name>[...]

        Where ``type`` could be either:
        - The pre-defined repository-based PURL type as defined in
        https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst

        - The supprted git service domains (e.g. ``github.com``) defined in ``available_domains``.

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
        # TODO: move this method to the repo finder in https://github.com/oracle/macaron/pull/388.
        domain = Analyzer.to_domain_from_known_purl_types(purl.type) or (
            purl.type if purl.type in available_domains else None
        )
        if not domain:
            logger.error("The PURL type of %s is not valid as a repository type.", purl.to_string())
            return None

        if not purl.namespace:
            logger.error("Expecting a non-empty namespace from %s.", purl.to_string())
            return None

        # TODO: Handle the version tag and commit digest if they are given in the PURL.
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

    class AnalysisTarget(NamedTuple):
        """Contains the resolved details of a software component to be analyzed.

        For repo_path, branch and digest, an empty string is used to indicated that they are not available. This is
        only for now because the current limitation of the Configuration class.
        """

        #: The parsed PackageURL object from the PackageURL string of the software component.
        #: This field will be None if no PackageURL string is provided for this component.
        parsed_purl: PackageURL | None

        #: The repository path of the software component.
        #: If the value repository path is not provided, it will be resolved from the PackageURL or empty if no
        #: repository is found.
        repo_path: str

        #: The branch of the repository to analyze.
        branch: str

        #: The digest of the commit to analyze.
        digest: str

    def add_component(
        self, config: Configuration, analysis: Analysis, existing_records: dict[str, Record] | None = None
    ) -> Component:
        """Add a software component if it does not exist in the DB already.

        The component instances are transient objects for SQLAlchemy, which may be
        added to the database ultimately.

        Parameters
        ----------
        config: Configuration
            The configuration for running Macaron.
        analysis: Analysis
            The current analysis instance.
        existing_records : dict[str, Record] | None
            The mapping of existing records that the analysis has run successfully.

        Returns
        -------
        Component
            The software component.

        Raises
        ------
        PURLNotFoundError
            No PURL is found for the component.
        DuplicateCmpError
            The component is already analyzed in the same session.
        """
        # Note: the component created in this function will be added to the database.
        available_domains = [git_service.hostname for git_service in GIT_SERVICES if git_service.hostname]
        try:
            analysis_target = Analyzer.to_analysis_target(config, available_domains)
        except InvalidPURLError as error:
            raise PURLNotFoundError("Invalid input PURL.") from error

        if not analysis_target.parsed_purl and not analysis_target.repo_path:
            raise PURLNotFoundError("Cannot determine the analysis as PURL and/or repository path is not provided.")

        repository = None
        if analysis_target.repo_path:
            git_obj = self._prepare_repo(
                os.path.join(self.output_path, self.GIT_REPOS_DIR),
                analysis_target.repo_path,
                analysis_target.branch,
                analysis_target.digest,
            )
            if git_obj:
                # TODO: use both the repo URL and the commit hash to check.
                if (
                    existing_records
                    and (existing_record := existing_records.get(git_url.get_remote_origin_of_local_repo(git_obj)))
                    is not None
                ):
                    raise DuplicateCmpError(
                        f"{analysis_target.repo_path} is already analyzed.", context=existing_record.context
                    )

                repository = self.add_repository(analysis_target.branch, git_obj)
            else:
                # We cannot prepare the repository even though we have successfully resolved the repository path for the
                # software component. If this happens, we don't raise error and treat the software component as if it
                # does not have any ``Repository`` attached to it.
                repository = None

        if not analysis_target.parsed_purl:
            # If the PURL is not available. This will only mean that the user don't provide PURL but only provide the
            # repository path for the software component. Therefore, the ``Repository`` instance is used to create a
            # unique PURL for it.
            if not repository:
                raise PURLNotFoundError(
                    f"The repository {analysis_target.repo_path} is not available and no PURL is provided from the user."
                )

            repo_snapshot_purl = PackageURL(
                type=repository.type,
                namespace=repository.owner,
                name=repository.name,
                version=repository.commit_sha,
            )
            return Component(purl=repo_snapshot_purl.to_string(), analysis=analysis, repository=repository)

        # If the PURL is available, we always create the software component with it whether the repository is
        # available or not.
        return Component(purl=analysis_target.parsed_purl.to_string(), analysis=analysis, repository=repository)

    @staticmethod
    def to_analysis_target(config: Configuration, available_domains: list[str]) -> AnalysisTarget:
        """Resolve the details of a software component from user input.

        Parameters
        ----------
        config : Configuration
            The target configuration that stores the user input values for the software component.
        available_domains : list[str]
            The list of supported git service host domain. This is used to convert repo-based PURL to a repository path
            of the corresponding software component.

        Returns
        -------
        AnalysisTarget
            The NamedTuple that contains the resolved details for the software component.

        Raises
        ------
        InvalidPURLError
            If the PURL provided from the user is invalid.
        """
        # Due to the current design of Configuration class. purl, repo_path, branch and digest are initialized
        # as empty strings and we assumed that they are always set with input values as non-empty strings.
        # Therefore, their true types are ``str``, and an empty string indicates that the input value is not provided.
        purl_input_str: str = config.get_value("purl")
        repo_path_input: str = config.get_value("path")
        input_branch: str = config.get_value("branch")
        input_digest: str = config.get_value("digest")

        match (purl_input_str, repo_path_input):
            case ("", ""):
                return Analyzer.AnalysisTarget(parsed_purl=None, repo_path="", branch="", digest="")

            case ("", _):
                # If only the repository path is provided, we will use the user-provided repository path to created the
                # ``Repository`` instance. Note that if this case happen, the software component will be initialized
                # with the PURL generated from the ``Repository`` instance (i.e. as a PURL pointing to a git repository
                # at a specific commit). For example: ``pkg:github.com/org/name@<commit_digest>``.
                return Analyzer.AnalysisTarget(
                    parsed_purl=None, repo_path=repo_path_input, branch=input_branch, digest=input_digest
                )

            case (_, ""):
                # If a PURL but no repository path are provided, we try to extract the repository path from the PURL.
                # Note that we can't always extract the repository path from any provided PURL.
                try:
                    parsed_purl = PackageURL.from_string(purl_input_str)
                except ValueError as error:
                    raise InvalidPURLError(f"The package url {purl_input_str} is not valid.") from error

                converted_repo_path = Analyzer.to_repo_path(parsed_purl, available_domains)
                # TODO: If ``converted_repo_path`` is None, this means that the PURL given by the user if not pointing
                # to a git repository (e.g ``pkg:maven/apache/maven@1.0.0``). Resolving the repository
                # path from such PURl string will be handled in https://github.com/oracle/macaron/pull/388.
                return Analyzer.AnalysisTarget(
                    parsed_purl=parsed_purl,
                    repo_path=converted_repo_path or "",
                    branch=input_branch,
                    digest=input_digest,
                )

            case (_, _):
                # If both the PURL and the repository are provided, we will use the user-provided repository path to
                # created the ``Repository`` instance later on. This ``Repository`` instance is attached to the
                # software component initialized from the user-provided PURL.
                try:
                    parsed_purl = PackageURL.from_string(purl_input_str)
                except ValueError as error:
                    raise InvalidPURLError(f"The package url {purl_input_str} is not valid.") from error

                return Analyzer.AnalysisTarget(
                    parsed_purl=parsed_purl, repo_path=repo_path_input, branch=input_branch, digest=input_digest
                )

            case _:
                return Analyzer.AnalysisTarget(parsed_purl=None, repo_path="", branch="", digest="")

    def get_analyze_ctx(self, component: Component) -> AnalyzeContext:
        """Return the analyze context for a target component.

        Parameters
        ----------
        component: Component
            The target software component.

        Returns
        -------
        AnalyzeContext
            The context of object of the target software component.
        """
        # Initialize the analyzing context for this repository.
        analyze_ctx = AnalyzeContext(
            component,
            global_config.macaron_path,
            self.output_path,
        )

        return analyze_ctx

    def _prepare_repo(
        self,
        target_dir: str,
        repo_path: str,
        branch_name: str = "",
        digest: str = "",
    ) -> Git | None:
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
        Git | None
            The pydriller.Git object of the repository or None if error.
        """
        # TODO: separate the logic for handling remote and local repos instead of putting them into this method.
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
        is_remote = git_url.is_remote_repo(repo_path)

        if is_remote:
            logger.info("The path to repo %s is a remote path.", repo_path)
            resolved_remote_path = git_url.get_remote_vcs_url(repo_path)
            if not resolved_remote_path:
                logger.error("The provided path to repo %s is not a valid remote path.", repo_path)
                return None

            git_service = self.get_git_service(resolved_remote_path)
            repo_unique_path = git_url.get_repo_dir_name(resolved_remote_path)
            resolved_local_path = os.path.join(target_dir, repo_unique_path)
            logger.info("Cloning the repository.")
            try:
                git_service.clone_repo(resolved_local_path, resolved_remote_path)
            except CloneError as error:
                logger.error("Cannot clone %s: %s", resolved_remote_path, str(error))
                return None
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

        # Checking out the specific branch or commit. This operation varies depends on the git service that the
        # repository uses.
        if not is_remote:
            # If the repo path provided by the user is a local path, we need to get the actual origin remote URL of
            # the repo to decide on the suitable git service.
            origin_remote_url = git_url.get_remote_origin_of_local_repo(git_obj)
            if git_url.is_remote_repo(origin_remote_url):
                # The local repo's origin remote url is a remote URL (e.g https://host.com/a/b): In this case, we obtain
                # the corresponding git service using ``self.get_git_service``.
                git_service = self.get_git_service(origin_remote_url)
            else:
                # The local repo's origin remote url is a local path (e.g /path/to/local/...). This happens when the
                # target repository is a clone from another local repo or is a clone from a git archive -
                # https://git-scm.com/docs/git-archive: In this case, we fall-back to the generic function
                # ``git_url.check_out_repo_target``.
                if not git_url.check_out_repo_target(git_obj, branch_name, digest, not is_remote):
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

    @staticmethod
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
        remote_path = analyze_ctx.component.repository.remote_path if analyze_ctx.component.repository else None
        git_service = self.get_git_service(remote_path)
        if isinstance(git_service, NoneGitService):
            logger.error("Unable to find repository or unsupported git service for %s", analyze_ctx.component.purl)
        else:
            logger.info(
                "Detected git service %s for %s.", git_service.name, analyze_ctx.component.repository.complete_name
            )
            analyze_ctx.dynamic_data["git_service"] = git_service

            # Determine the build tool.
            for build_tool in BUILD_TOOLS:
                build_tool.load_defaults()
                logger.info(
                    "Checking if the repo %s uses build tool %s",
                    analyze_ctx.component.repository.complete_name,
                    build_tool.name,
                )

                if build_tool.is_detected(analyze_ctx.component.repository.fs_path):
                    logger.info("The repo uses %s build tool.", build_tool.name)
                    analyze_ctx.dynamic_data["build_spec"]["tools"].append(build_tool)

            if not analyze_ctx.dynamic_data["build_spec"]["tools"]:
                logger.info(
                    "Cannot discover any build tools for %s or the build tools are not supported.",
                    analyze_ctx.component.repository.complete_name,
                )

            # Determine the CI services.
            for ci_service in CI_SERVICES:
                ci_service.load_defaults()
                ci_service.set_api_client()

                if ci_service.is_detected(
                    repo_path=analyze_ctx.component.repository.fs_path,
                    git_service=analyze_ctx.dynamic_data["git_service"],
                ):
                    logger.info("The repo uses %s CI service.", ci_service.name)

                    # Parse configuration files and generate IRs.
                    # Add the bash commands to the context object to be used by other checks.
                    callgraph = ci_service.build_call_graph(
                        analyze_ctx.component.repository.fs_path,
                        os.path.relpath(analyze_ctx.component.repository.fs_path, analyze_ctx.output_dir),
                    )
                    bash_commands = list(ci_service.extract_all_bash(callgraph)) if callgraph else []
                    analyze_ctx.dynamic_data["ci_services"].append(
                        CIInfo(
                            service=ci_service,
                            bash_commands=bash_commands,
                            callgraph=callgraph,
                            provenance_assets=[],
                            latest_release={},
                            provenances=[InTotoV01Payload(statement=Provenance().payload)],
                        )
                    )

        # Determine the package registries.
        # We match the repo against package registries through build tools.
        build_tools = analyze_ctx.dynamic_data["build_spec"]["tools"]
        for package_registry in PACKAGE_REGISTRIES:
            for build_tool in build_tools:
                if package_registry.is_detected(build_tool):
                    analyze_ctx.dynamic_data["package_registries"].append(
                        PackageRegistryInfo(
                            build_tool=build_tool,
                            package_registry=package_registry,
                        )
                    )

        # TODO: Get the list of skipped checks from user configuration
        skipped_checks: list[SkippedInfo] = []

        results = registry.scan(analyze_ctx, skipped_checks)

        return results


class DuplicateCmpError(DuplicateError):
    """This class is used for duplicated software component errors."""

    def __init__(self, *args, context: AnalyzeContext | None = None, **kwargs) -> None:  # type: ignore[no-untyped-def]
        """Create a DuplicateCmpError instance.

        Parameters
        ----------
        context: AnalyzeContext | None
            The context in which the exception is raised.
        """
        super().__init__(*args, **kwargs)
        self.context: AnalyzeContext | None = context
