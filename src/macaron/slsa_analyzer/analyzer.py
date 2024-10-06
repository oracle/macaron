# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module handles the cloning and analyzing a Git repo."""
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

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
from macaron.database.table_definitions import Analysis, Component, ProvenanceSubject, Repository
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer, DependencyInfo
from macaron.errors import (
    CloneError,
    DuplicateError,
    InvalidAnalysisTargetError,
    InvalidPURLError,
    ProvenanceError,
    PURLNotFoundError,
    RepoCheckOutError,
)
from macaron.output_reporter.reporter import FileReporter
from macaron.output_reporter.results import Record, Report, SCMStatus
from macaron.repo_finder import repo_finder
from macaron.repo_finder.commit_finder import find_commit
from macaron.repo_finder.provenance_extractor import (
    check_if_input_purl_provenance_conflict,
    check_if_input_repo_provenance_conflict,
    extract_repo_and_commit_from_provenance,
)
from macaron.repo_finder.provenance_finder import ProvenanceFinder, find_provenance_from_ci
from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.asset import VirtualReleaseAsset
from macaron.slsa_analyzer.build_tool import BUILD_TOOLS

# To load all checks into the registry
from macaron.slsa_analyzer.checks import *  # pylint: disable=wildcard-import,unused-wildcard-import # noqa: F401,F403
from macaron.slsa_analyzer.ci_service import CI_SERVICES
from macaron.slsa_analyzer.database_store import store_analyze_context_to_db
from macaron.slsa_analyzer.git_service import GIT_SERVICES, BaseGitService
from macaron.slsa_analyzer.git_service.base_git_service import NoneGitService
from macaron.slsa_analyzer.package_registry import PACKAGE_REGISTRIES
from macaron.slsa_analyzer.provenance.expectations.expectation_registry import ExpectationRegistry
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, InTotoV01Payload
from macaron.slsa_analyzer.provenance.slsa import SLSAProvenanceData
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

        logger.info(
            "The following checks are excluded based on the user configuration: %s",
            [check for check in registry.get_all_checks_mapping() if check not in registry.checks_to_run],
        )
        logger.info("The following checks will be run: %s", registry.checks_to_run)

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

    def run(
        self,
        user_config: dict,
        sbom_path: str = "",
        deps_depth: int = 0,
        provenance_payload: InTotoPayload | None = None,
    ) -> int:
        """Run the analysis and write results to the output path.

        This method handles the configuration file and writes the result html reports including dependencies.
        The return status code of this method depends on the analyzing status of the main repo only.

        Parameters
        ----------
        user_config : dict
            The dictionary that contains the user config parsed from the yaml file.
        sbom_path : str
            The path to the SBOM.
        deps_depth : int
            The depth of dependency resolution. Default: 0.
        provenance_payload : InToToPayload | None
            The provenance intoto payload for the main software component.

        Returns
        -------
        int
            The return status code.
        """
        main_config = Configuration(user_config.get("target", {}))
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
                main_record = self.run_single(
                    main_config,
                    analysis,
                    provenance_payload=provenance_payload,
                )

                if main_record.status != SCMStatus.AVAILABLE or not main_record.context:
                    logger.info("Analysis has failed.")
                    return os.EX_DATAERR

                if deps_depth == 0:
                    logger.info("Skipping automatic dependency analysis...")
                elif deps_depth == 1:
                    # Run the chosen dependency analyzer plugin on direct dependencies.
                    deps_resolved = DependencyAnalyzer.resolve_dependencies(
                        main_record.context,
                        sbom_path,
                        recursive=False,
                    )
                elif deps_depth == -1:
                    # Run the chosen dependency analyzer plugin on transitive dependencies.
                    deps_resolved = DependencyAnalyzer.resolve_dependencies(
                        main_record.context,
                        sbom_path,
                        recursive=True,
                    )
                else:
                    # Can't reach here.
                    logger.critical("Expecting deps depth to be '0', '1' or '-1', got %s", deps_depth)
                    return os.EX_USAGE

                # Merge the automatically resolved dependencies with the manual configuration.
                deps_config = DependencyAnalyzer.to_configs(deps_resolved)

                # Create a report instance with the record of the main repo.
                report = Report(main_record)

                duplicated_scm_records: list[Record] = []

                if deps_config:
                    logger.info("Start analyzing the dependencies.")
                    for config in deps_config:
                        dep_status: SCMStatus = config.get_value("available")
                        if dep_status == SCMStatus.DUPLICATED_SCM:
                            dep_record: Record = Record(
                                record_id=config.get_value("id"),
                                description=config.get_value("note"),
                                pre_config=config,
                                status=config.get_value("available"),
                            )
                            report.add_dep_record(dep_record)
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

    def run_single(
        self,
        config: Configuration,
        analysis: Analysis,
        existing_records: dict[str, Record] | None = None,
        provenance_payload: InTotoPayload | None = None,
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
        provenance_payload : InToToPayload | None
            The provenance intoto payload for the analyzed software component.

        Returns
        -------
        Record
            The record of the analysis for this repository.
        """
        # Parse the PURL.
        repo_id = config.get_value("id")
        try:
            parsed_purl = Analyzer.parse_purl(config)
            # Validate PURL type as per https://github.com/package-url/purl-spec/blob/master/PURL-SPECIFICATION.rst
            if parsed_purl and not re.match(r"^[a-z.+-][a-z0-9.+-]*$", parsed_purl.type):
                raise InvalidPURLError(f"Invalid purl type: {parsed_purl.type}")
        except InvalidPURLError as error:
            logger.error(error)
            return Record(
                record_id=repo_id,
                description=str(error),
                pre_config=config,
                status=SCMStatus.ANALYSIS_FAILED,
            )

        provenance_is_verified = False
        if not provenance_payload and parsed_purl:
            # Try to find the provenance file for the parsed PURL.
            provenance_finder = ProvenanceFinder()
            provenances = provenance_finder.find_provenance(parsed_purl)
            if provenances:
                provenance_payload = provenances[0]
                if defaults.getboolean("analyzer", "verify_provenance"):
                    provenance_is_verified = provenance_finder.verify_provenance(parsed_purl, provenances)

        # Try to extract the repository URL and commit digest from the Provenance, if it exists.
        repo_path_input: str | None = config.get_value("path")
        digest_input: str | None = config.get_value("digest")
        provenance_repo_url = provenance_commit_digest = None
        if provenance_payload:
            try:
                provenance_repo_url, provenance_commit_digest = extract_repo_and_commit_from_provenance(
                    provenance_payload
                )
            except ProvenanceError as error:
                logger.debug("Failed to extract repo or commit from provenance: %s", error)

            # Try to validate the input repo against provenance contents.
            if provenance_repo_url and check_if_input_repo_provenance_conflict(repo_path_input, provenance_repo_url):
                return Record(
                    record_id=repo_id,
                    description="Input mismatch between repo and provenance.",
                    pre_config=config,
                    status=SCMStatus.ANALYSIS_FAILED,
                )

        # Create the analysis target.
        available_domains = [git_service.hostname for git_service in GIT_SERVICES if git_service.hostname]
        try:
            analysis_target = Analyzer.to_analysis_target(
                config, available_domains, parsed_purl, provenance_repo_url, provenance_commit_digest
            )
        except InvalidAnalysisTargetError as error:
            return Record(
                record_id=repo_id,
                description=str(error),
                pre_config=config,
                status=SCMStatus.ANALYSIS_FAILED,
            )

        # Prepare the repo.
        git_obj = None
        if analysis_target.repo_path:
            git_obj = self._prepare_repo(
                os.path.join(self.output_path, self.GIT_REPOS_DIR),
                analysis_target.repo_path,
                analysis_target.branch,
                analysis_target.digest,
                analysis_target.parsed_purl,
            )

        # Check if only one of the repo or digest came from direct input.
        if git_obj and (provenance_repo_url or provenance_commit_digest) and parsed_purl:
            if check_if_input_purl_provenance_conflict(
                git_obj,
                bool(repo_path_input),
                bool(digest_input),
                provenance_repo_url,
                provenance_commit_digest,
                parsed_purl,
            ):
                return Record(
                    record_id=repo_id,
                    description="Input mismatch between repo/commit (purl) and provenance.",
                    pre_config=config,
                    status=SCMStatus.ANALYSIS_FAILED,
                )

        # Create the component.
        try:
            component = self.add_component(
                analysis,
                analysis_target,
                git_obj,
                existing_records,
                provenance_payload,
            )
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

        git_service = self._determine_git_service(analyze_ctx)
        self._determine_ci_services(analyze_ctx, git_service)
        self._determine_build_tools(analyze_ctx, git_service)
        self._determine_package_registries(analyze_ctx)

        if not provenance_payload:
            # Look for provenance using the CI.
            provenance_payload = find_provenance_from_ci(analyze_ctx, git_obj)
            # If found, verify analysis target against new provenance
            if provenance_payload:
                # If repository URL was not provided as input, check the one found during analysis.
                if not repo_path_input and component.repository:
                    repo_path_input = component.repository.remote_path

                # Extract the digest and repository URL from provenance.
                provenance_repo_url = provenance_commit_digest = None
                try:
                    provenance_repo_url, provenance_commit_digest = extract_repo_and_commit_from_provenance(
                        provenance_payload
                    )
                except ProvenanceError as error:
                    logger.debug("Failed to extract repo or commit from provenance: %s", error)

                # Try to validate the input repo against provenance contents.
                if provenance_repo_url and check_if_input_repo_provenance_conflict(
                    repo_path_input, provenance_repo_url
                ):
                    return Record(
                        record_id=repo_id,
                        description="Input mismatch between repo/commit and provenance.",
                        pre_config=config,
                        status=SCMStatus.ANALYSIS_FAILED,
                    )

        analyze_ctx.dynamic_data["provenance"] = provenance_payload
        if provenance_payload:
            analyze_ctx.dynamic_data["is_inferred_prov"] = False
            analyze_ctx.dynamic_data["provenance_verified"] = provenance_is_verified
        analyze_ctx.dynamic_data["provenance_repo_url"] = provenance_repo_url
        analyze_ctx.dynamic_data["provenance_commit_digest"] = provenance_commit_digest

        analyze_ctx.check_results = registry.scan(analyze_ctx)

        return Record(
            record_id=repo_id,
            description="Analysis Completed.",
            pre_config=config,
            status=SCMStatus.AVAILABLE,
            context=analyze_ctx,
        )

    def add_repository(self, branch_name: str | None, git_obj: Git) -> Repository | None:
        """Create a repository instance for a target repository.

        The repository instances are transient objects for SQLAlchemy, which may be
        added to the database ultimately.

        Parameters
        ----------
        branch_name : str | None
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

        if branch_name:
            res_branch = branch_name
        else:
            try:
                res_branch = git_obj.repo.active_branch.name
            except TypeError as err:
                # HEAD is a detached symbolic reference. This happens when we checkout a commit.
                # However, it shouldn't happen as we don't allow specifying a commit digest without
                # a branch in the config.
                logger.debug("The HEAD of the repo does not point to any branch: %s.", err)
                res_branch = None

        logger.debug("Branch: %s", res_branch)

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
        self,
        analysis: Analysis,
        analysis_target: AnalysisTarget,
        git_obj: Git | None,
        existing_records: dict[str, Record] | None = None,
        provenance_payload: InTotoPayload | None = None,
    ) -> Component:
        """Add a software component if it does not exist in the DB already.

        The component instances are transient objects for SQLAlchemy, which may be
        added to the database ultimately.

        Parameters
        ----------
        analysis: Analysis
            The current analysis instance.
        analysis_target: AnalysisTarget
            The target of this analysis.
        git_obj: Git | None
            The pydriller.Git object of the repository.
        existing_records : dict[str, Record] | None
            The mapping of existing records that the analysis has run successfully.
        provenance_payload: InTotoVPayload | None
            The provenance intoto payload for the analyzed software component.

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
            purl = PackageURL(
                type=repository.type,
                namespace=repository.owner,
                name=repository.name,
                version=repository.commit_sha,
            )
        else:
            # If the PURL is available, we always create the software component with it whether the repository is
            # available or not.
            purl = analysis_target.parsed_purl

        component = Component(
            purl=str(purl),
            analysis=analysis,
            repository=repository,
        )

        if provenance_payload:
            component.provenance_subject = ProvenanceSubject.from_purl_and_provenance(
                purl=purl,
                provenance_payload=provenance_payload,
            )

        return component

    @staticmethod
    def parse_purl(config: Configuration) -> PackageURL | None:
        """Parse the PURL provided in the input.

        Parameters
        ----------
        config : Configuration
            The target configuration that stores the user input values for the software component.

        Returns
        -------
        PackageURL | None
            The parsed PURL, or None if one was not provided as input.

        Raises
        ------
        InvalidPURLError
            If the PURL provided from the user is invalid.
        """
        # Due to the current design of Configuration class, repo_path, branch and digest are initialized
        # as empty strings, and we assumed that they are always set with input values as non-empty strings.
        # Therefore, their true types are ``str``, and an empty string indicates that the input value is not provided.
        # The purl might be a PackageURL type, a string, or None, which should be reduced down to an optional
        # PackageURL type.
        purl = config.get_value("purl")
        if purl is None or purl == "":
            return None
        if isinstance(purl, PackageURL):
            return purl
        try:
            # Note that PackageURL.from_string sanitizes the unsafe characters in the purl string,
            # which is user-controllable, by calling urllib's `urlsplit` function.
            return PackageURL.from_string(purl)
        except ValueError as error:
            raise InvalidPURLError(f"Invalid input PURL: {purl}") from error

    @staticmethod
    def to_analysis_target(
        config: Configuration,
        available_domains: list[str],
        parsed_purl: PackageURL | None,
        provenance_repo_url: str | None = None,
        provenance_commit_digest: str | None = None,
    ) -> AnalysisTarget:
        """Resolve the details of a software component from user input.

        Parameters
        ----------
        config : Configuration
            The target configuration that stores the user input values for the software component.
        available_domains : list[str]
            The list of supported git service host domain. This is used to convert repo-based PURL to a repository path
            of the corresponding software component.
        parsed_purl: PackageURL | None
            The PURL to use for the analysis target, or None if one has not been provided.
        provenance_repo_url: str | None
            The repository URL extracted from provenance, or None if not found or no provenance.
        provenance_commit_digest: str | None
            The commit extracted from provenance, or None if not found or no provenance.

        Returns
        -------
        AnalysisTarget
            The NamedTuple that contains the resolved details for the software component.

        Raises
        ------
        InvalidAnalysisTargetError
            Raised if a valid Analysis Target cannot be created.
        """
        repo_path_input: str = config.get_value("path")
        input_branch: str = config.get_value("branch")
        input_digest: str = config.get_value("digest")

        match (parsed_purl, repo_path_input):
            case (None, ""):
                raise InvalidAnalysisTargetError(
                    "Cannot determine the analysis target: PURL and repository path are missing."
                )

            case (_, ""):
                # If a PURL but no repository path is provided, we try to extract the repository path from the PURL.
                # Note that we can't always extract the repository path from any provided PURL.
                converted_repo_path = None
                repo: str | None = None
                # parsed_purl cannot be None here, but mypy cannot detect that without some extra help.
                if parsed_purl is not None:
                    if provenance_repo_url or provenance_commit_digest:
                        return Analyzer.AnalysisTarget(
                            parsed_purl=parsed_purl,
                            repo_path=provenance_repo_url or "",
                            branch="",
                            digest=provenance_commit_digest or "",
                        )

                    # As there is no repo or commit from provenance, use the Repo Finder to find the repo.
                    converted_repo_path = repo_finder.to_repo_path(parsed_purl, available_domains)
                    if converted_repo_path is None:
                        # Try to find repo from PURL
                        repo = repo_finder.find_repo(parsed_purl)

                return Analyzer.AnalysisTarget(
                    parsed_purl=parsed_purl,
                    repo_path=converted_repo_path or repo or "",
                    branch=input_branch,
                    digest=input_digest,
                )

            case (_, _) | (None, _):
                # 1. If only the repository path is provided, we will use the user-provided repository path to create
                # the``Repository`` instance. Note that if this case happen, the software component will be initialized
                # with the PURL generated from the ``Repository`` instance (i.e. as a PURL pointing to a git repository
                # at a specific commit). For example: ``pkg:github.com/org/name@<commit_digest>``.
                # 2. If both the PURL and the repository are provided, we will use the user-provided repository path to
                # create the ``Repository`` instance later on. This ``Repository`` instance is attached to the
                # software component initialized from the user-provided PURL.
                # For both cases, the digest will be the user input digest if it is provided. If not, it will be taken
                # from the provenance if the provenance is available.
                if input_digest:
                    return Analyzer.AnalysisTarget(
                        parsed_purl=parsed_purl,
                        repo_path=repo_path_input,
                        branch=input_branch,
                        digest=input_digest,
                    )

                return Analyzer.AnalysisTarget(
                    parsed_purl=parsed_purl,
                    repo_path=repo_path_input,
                    branch=input_branch,
                    digest=provenance_commit_digest or "",
                )

            case _:
                # Even though this case is unnecessary, it is still put here because mypy cannot type-narrow tuples
                # correctly (see https://github.com/python/mypy/pull/16905, which was fixed, but not released).
                raise InvalidAnalysisTargetError(
                    "Cannot determine the analysis target: PURL and repository path are missing."
                )

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
        purl: PackageURL | None = None,
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
            logger.info("Checking if the path to repo %s is a local path.", repo_path)
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

        # Find the digest and branch if a version has been specified
        if not digest and purl and purl.version:
            found_digest = find_commit(git_obj, purl)
            if not found_digest:
                logger.error(
                    "Could not map the input purl string to a specific commit in the corresponding repository."
                )
                return None
            digest = found_digest

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
        # Because strict mode is enabled, if a path doesn't exist or a symlink loop
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

    def _determine_git_service(self, analyze_ctx: AnalyzeContext) -> BaseGitService:
        """Determine the Git service used by the software component."""
        remote_path = analyze_ctx.component.repository.remote_path if analyze_ctx.component.repository else None
        git_service = self.get_git_service(remote_path)

        if isinstance(git_service, NoneGitService):
            logger.info("Unable to find repository or unsupported git service for %s", analyze_ctx.component.purl)
        else:
            logger.info(
                "Detected git service %s for %s.", git_service.name, analyze_ctx.component.repository.complete_name
            )
            analyze_ctx.dynamic_data["git_service"] = git_service

        return git_service

    def _determine_build_tools(self, analyze_ctx: AnalyzeContext, git_service: BaseGitService) -> None:
        """Determine the build tools that match the software component's PURL type."""
        for build_tool in BUILD_TOOLS:
            build_tool.load_defaults()
            if build_tool.purl_type == analyze_ctx.component.type:
                logger.debug(
                    "Found %s build tool based on the %s PackageURL.", build_tool.name, analyze_ctx.component.purl
                )
                analyze_ctx.dynamic_data["build_spec"]["purl_tools"].append(build_tool)

            if isinstance(git_service, NoneGitService):
                continue

            if not analyze_ctx.component.repository:
                continue

            logger.info(
                "Checking if the repo %s uses build tool %s",
                analyze_ctx.component.repository.complete_name,
                build_tool.name,
            )

            if build_tool.is_detected(analyze_ctx.component.repository.fs_path):
                logger.info("The repo uses %s build tool.", build_tool.name)
                analyze_ctx.dynamic_data["build_spec"]["tools"].append(build_tool)

        if not analyze_ctx.dynamic_data["build_spec"]["tools"]:
            if analyze_ctx.component.repository:
                logger.info(
                    "Unable to discover any build tools for repository %s or the build tools are not supported.",
                    analyze_ctx.component.repository.complete_name,
                )
            else:
                logger.info("Unable to discover build tools because repository is None.")

    def _determine_ci_services(self, analyze_ctx: AnalyzeContext, git_service: BaseGitService) -> None:
        """Determine the CI services used by the software component."""
        if isinstance(git_service, NoneGitService):
            return

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
                analyze_ctx.dynamic_data["ci_services"].append(
                    CIInfo(
                        service=ci_service,
                        callgraph=callgraph,
                        provenance_assets=[],
                        release={},
                        provenances=[
                            SLSAProvenanceData(
                                payload=InTotoV01Payload(statement=Provenance().payload),
                                asset=VirtualReleaseAsset(name="No_ASSET", url="NO_URL", size_in_bytes=0),
                            )
                        ],
                        build_info_results=InTotoV01Payload(statement=Provenance().payload),
                    )
                )

    def _determine_package_registries(self, analyze_ctx: AnalyzeContext) -> None:
        """Determine the package registries used by the software component based on its build tools."""
        build_tools = (
            analyze_ctx.dynamic_data["build_spec"]["tools"] or analyze_ctx.dynamic_data["build_spec"]["purl_tools"]
        )
        for package_registry in PACKAGE_REGISTRIES:
            for build_tool in build_tools:
                if package_registry.is_detected(build_tool):
                    analyze_ctx.dynamic_data["package_registries"].append(
                        PackageRegistryInfo(
                            build_tool=build_tool,
                            package_registry=package_registry,
                        )
                    )


class DuplicateCmpError(DuplicateError):
    """This class is used for duplicated software component errors."""

    def __init__(self, *args: Any, context: AnalyzeContext | None = None, **kwargs: Any) -> None:
        """Create a DuplicateCmpError instance.

        Parameters
        ----------
        context: AnalyzeContext | None
            The context in which the exception is raised.
        """
        super().__init__(*args, **kwargs)
        self.context: AnalyzeContext | None = context
