# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module handles the cloning and analyzing a Git repo."""

import glob
import logging
import os
import re
import sys
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

import sqlalchemy.exc
from packageurl import PackageURL
from pydriller.git import Git
from sqlalchemy.orm import Session

from macaron import __version__
from macaron.artifact.local_artifact import (
    get_local_artifact_dirs,
    get_local_artifact_hash,
)
from macaron.config.global_config import global_config
from macaron.config.target_config import Configuration
from macaron.database.database_manager import DatabaseManager, get_db_manager, get_db_session
from macaron.database.table_definitions import (
    Analysis,
    Component,
    Provenance,
    ProvenanceSubject,
    RepoFinderMetadata,
    Repository,
)
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer, DependencyInfo
from macaron.errors import (
    DuplicateError,
    InvalidAnalysisTargetError,
    InvalidPURLError,
    LocalArtifactFinderError,
    ProvenanceError,
    PURLNotFoundError,
)
from macaron.json_tools import json_extract
from macaron.output_reporter.reporter import FileReporter
from macaron.output_reporter.results import Record, Report, SCMStatus
from macaron.provenance import provenance_verifier
from macaron.provenance.provenance_extractor import (
    check_if_input_purl_provenance_conflict,
    check_if_input_repo_provenance_conflict,
    extract_predicate_version,
    extract_repo_and_commit_from_provenance,
)
from macaron.provenance.provenance_finder import ProvenanceFinder, find_provenance_from_ci
from macaron.provenance.provenance_verifier import determine_provenance_slsa_level, verify_ci_provenance
from macaron.repo_finder import repo_finder
from macaron.repo_finder.repo_finder import prepare_repo
from macaron.repo_finder.repo_finder_enums import CommitFinderInfo, RepoFinderInfo
from macaron.repo_finder.repo_utils import get_git_service
from macaron.repo_verifier.repo_verifier import verify_repo
from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.asset import VirtualReleaseAsset
from macaron.slsa_analyzer.build_tool import BUILD_TOOLS

# To load all checks into the registry
from macaron.slsa_analyzer.checks import *  # pylint: disable=wildcard-import,unused-wildcard-import # noqa: F401,F403
from macaron.slsa_analyzer.ci_service import CI_SERVICES
from macaron.slsa_analyzer.database_store import store_analyze_context_to_db
from macaron.slsa_analyzer.git_service import GIT_SERVICES, BaseGitService, GitHub
from macaron.slsa_analyzer.git_service.base_git_service import NoneGitService
from macaron.slsa_analyzer.git_url import GIT_REPOS_DIR
from macaron.slsa_analyzer.package_registry import PACKAGE_REGISTRIES, MavenCentralRegistry, PyPIRegistry
from macaron.slsa_analyzer.package_registry.pypi_registry import find_or_create_pypi_asset
from macaron.slsa_analyzer.provenance.expectations.expectation_registry import ExpectationRegistry
from macaron.slsa_analyzer.provenance.intoto import (
    InTotoPayload,
    InTotoV01Payload,
    ValidateInTotoPayloadError,
    validate_intoto_payload,
)
from macaron.slsa_analyzer.provenance.loader import decode_provenance
from macaron.slsa_analyzer.provenance.slsa import SLSAProvenanceData
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from macaron.slsa_analyzer.specs.inferred_provenance import InferredProvenance
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


class Analyzer:
    """This class is used to analyze SLSA levels of a Git repo."""

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

        # Load the expectations from global config.
        self.expectations = ExpectationRegistry(global_config.expectation_paths)

        # Initialize the reporters to store analysis data to files.
        self.reporters: list[FileReporter] = []

        # Get the db manager singleton object.
        self.db_man: DatabaseManager = get_db_manager()

        # Create database tables: all checks have been registered so all tables should be mapped now
        self.db_man.create_tables()

        self.local_artifact_repo_mapper = Analyzer._get_local_artifact_repo_mapper()

    def run(
        self,
        user_config: dict,
        sbom_path: str = "",
        deps_depth: int = 0,
        provenance_payload: InTotoPayload | None = None,
        verify_provenance: bool = False,
        analyze_source: bool = False,
        force_analyze_source: bool = False,
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
        verify_provenance: bool
            Enable provenance verification if True.
        analyze_source : bool
            When true, triggers source code analysis for PyPI packages. Defaults to False.
        force_analyze_source : bool
            When true, enforces running source code analysis regardless of other heuristic results. Defaults to False.

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
                    verify_provenance=verify_provenance,
                    analyze_source=analyze_source,
                    force_analyze_source=force_analyze_source,
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
                logger.debug(str(report))

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
        verify_provenance: bool = False,
        analyze_source: bool = False,
        force_analyze_source: bool = False,
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
        verify_provenance: bool
            Enable provenance verification if True.
        analyze_source : bool
            When true, triggers source code analysis for PyPI packages. Defaults to False.
        force_analyze_source : bool
            When true, enforces running source code analysis regardless of other heuristic results. Defaults to False.

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

        # Pre-populate all package registries so assets can be stored for later.
        package_registries_info = self._populate_package_registry_info()

        provenance_is_verified = False
        provenance_asset = None
        if not provenance_payload and parsed_purl:
            # Try to find the provenance file for the parsed PURL.
            provenance_finder = ProvenanceFinder()
            provenances = provenance_finder.find_provenance(parsed_purl)
            if provenances:
                provenance_asset = provenances[0]
                provenance_payload = provenance_asset.payload
                if provenance_payload.verified:
                    provenance_is_verified = True
                if verify_provenance:
                    provenance_is_verified = provenance_verifier.verify_provenance(parsed_purl, provenances)

        # Try to extract the repository URL and commit digest from the Provenance, if it exists.
        repo_path_input: str | None = config.get_value("path")
        provenance_repo_url = provenance_commit_digest = None
        if provenance_payload:
            try:
                provenance_repo_url, provenance_commit_digest = extract_repo_and_commit_from_provenance(
                    provenance_payload
                )
            except ProvenanceError as error:
                logger.debug("Failed to extract from provenance: %s", error)
            if check_if_input_repo_provenance_conflict(repo_path_input, provenance_repo_url):
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
                config,
                available_domains,
                parsed_purl,
                provenance_repo_url,
                provenance_commit_digest,
                package_registries_info,
            )
        except InvalidAnalysisTargetError as error:
            return Record(
                record_id=repo_id,
                description=str(error),
                pre_config=config,
                status=SCMStatus.ANALYSIS_FAILED,
            )

        local_artifact_dirs = None
        if parsed_purl and parsed_purl.type in self.local_artifact_repo_mapper:
            local_artifact_repo_path = self.local_artifact_repo_mapper[parsed_purl.type]
            try:
                local_artifact_dirs = get_local_artifact_dirs(
                    purl=parsed_purl,
                    local_artifact_repo_path=local_artifact_repo_path,
                )
            except LocalArtifactFinderError as error:
                logger.debug(error)

        # Prepare the repo.
        git_obj = None
        commit_finder_outcome = CommitFinderInfo.NOT_USED
        final_digest = analysis_target.digest
        if analysis_target.repo_path:
            git_obj, commit_finder_outcome = prepare_repo(
                os.path.join(self.output_path, GIT_REPOS_DIR),
                analysis_target.repo_path,
                analysis_target.branch,
                analysis_target.digest,
                analysis_target.parsed_purl,
            )
            if git_obj:
                final_digest = git_obj.get_head().hash

        repo_finder_metadata = RepoFinderMetadata(
            repo_finder_outcome=analysis_target.repo_finder_outcome,
            commit_finder_outcome=commit_finder_outcome,
            found_url=analysis_target.repo_path,
            found_commit=final_digest,
        )

        # Check if repo came from direct input.
        if parsed_purl:
            if check_if_input_purl_provenance_conflict(
                bool(repo_path_input),
                provenance_repo_url,
                parsed_purl,
            ):
                return Record(
                    record_id=repo_id,
                    description="Input mismatch between repo (purl) and provenance.",
                    pre_config=config,
                    status=SCMStatus.ANALYSIS_FAILED,
                )

        # Create the component.
        try:
            component = self.add_component(
                analysis,
                analysis_target,
                git_obj,
                repo_finder_metadata,
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

        analyze_ctx = self.create_analyze_ctx(component)
        analyze_ctx.dynamic_data["expectation"] = self.expectations.get_expectation_for_target(
            analyze_ctx.component.purl.split("@")[0]
        )

        git_service = self._determine_git_service(analyze_ctx)
        self._determine_ci_services(analyze_ctx, git_service)
        self._determine_build_tools(analyze_ctx, git_service)

        # Try to find an attestation from GitHub, if applicable.
        if parsed_purl and not provenance_payload and analysis_target.repo_path and isinstance(git_service, GitHub):
            # Try to discover GitHub attestation for the target software component.
            artifact_hash = self.get_artifact_hash(parsed_purl, local_artifact_dirs, package_registries_info)
            if artifact_hash:
                provenance_payload = self.get_github_attestation_payload(analyze_ctx, git_service, artifact_hash)

        if parsed_purl is not None:
            self._verify_repository_link(parsed_purl, analyze_ctx)
        self._determine_package_registries(analyze_ctx, package_registries_info)

        provenance_l3_verified = False
        if not provenance_payload:
            # Look for provenance using the CI.
            with tempfile.TemporaryDirectory() as temp_dir:
                provenance_asset = find_provenance_from_ci(analyze_ctx, git_obj, temp_dir)
                # If found, validate analysis target against new provenance.
                if provenance_asset:
                    # If repository URL was not provided as input, check the one found during analysis.
                    provenance_payload = provenance_asset.payload
                    if not repo_path_input and component.repository:
                        repo_path_input = component.repository.remote_path
                    provenance_repo_url = provenance_commit_digest = None
                    try:
                        provenance_repo_url, provenance_commit_digest = extract_repo_and_commit_from_provenance(
                            provenance_payload
                        )
                    except ProvenanceError as error:
                        logger.debug("Failed to extract from provenance: %s", error)

                    if check_if_input_repo_provenance_conflict(repo_path_input, provenance_repo_url):
                        return Record(
                            record_id=repo_id,
                            description="Input mismatch between repo/commit and provenance.",
                            pre_config=config,
                            status=SCMStatus.ANALYSIS_FAILED,
                        )

                    # Also try to verify CI provenance contents.
                    if verify_provenance:
                        verified = []
                        for ci_info in analyze_ctx.dynamic_data["ci_services"]:
                            verified.append(verify_ci_provenance(analyze_ctx, ci_info, temp_dir))
                            if not verified:
                                break
                        if verified and all(verified):
                            provenance_l3_verified = True

        if provenance_payload:
            analyze_ctx.dynamic_data["is_inferred_prov"] = False
            slsa_version = extract_predicate_version(provenance_payload)

            slsa_level = determine_provenance_slsa_level(
                analyze_ctx, provenance_payload, provenance_is_verified, provenance_l3_verified
            )

            analyze_ctx.dynamic_data["provenance_info"] = Provenance(
                component=component,
                repository_url=provenance_repo_url,
                commit_sha=provenance_commit_digest,
                verified=provenance_is_verified,
                provenance_payload=provenance_payload,
                slsa_level=slsa_level,
                slsa_version=slsa_version,
                provenance_asset_name=provenance_asset.name if provenance_asset else None,
                provenance_asset_url=provenance_asset.url if provenance_asset else None,
                # TODO Add release digest.
            )

        analyze_ctx.dynamic_data["analyze_source"] = analyze_source
        analyze_ctx.dynamic_data["force_analyze_source"] = force_analyze_source

        if local_artifact_dirs:
            analyze_ctx.dynamic_data["local_artifact_paths"].extend(local_artifact_dirs)

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

        #: The outcome of the Repo Finder on this analysis target.
        repo_finder_outcome: RepoFinderInfo

    def add_component(
        self,
        analysis: Analysis,
        analysis_target: AnalysisTarget,
        git_obj: Git | None,
        repo_finder_metadata: RepoFinderMetadata,
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
        repo_finder_metadata: RepoFinderMetadata
            The Repo Finder metadata for this component.
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
            repo_finder_metadata=repo_finder_metadata,
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
        package_registries_info: list[PackageRegistryInfo] | None = None,
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
        package_registries_info: list[PackageRegistryInfo] | None
            The list of package registry information if available.
            If no package registries are loaded, this can be set to None.

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
        repo_finder_outcome = RepoFinderInfo.NOT_USED

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
                            repo_finder_outcome=repo_finder_outcome,
                        )

                    # As there is no repo or commit from provenance, use the Repo Finder to find the repo.
                    converted_repo_path = repo_finder.to_repo_path(parsed_purl, available_domains)
                    if converted_repo_path is None:
                        # Try to find repo from PURL
                        repo, repo_finder_outcome = repo_finder.find_repo(
                            parsed_purl, package_registries_info=package_registries_info
                        )

                return Analyzer.AnalysisTarget(
                    parsed_purl=parsed_purl,
                    repo_path=converted_repo_path or repo or "",
                    branch=input_branch,
                    digest=input_digest,
                    repo_finder_outcome=repo_finder_outcome,
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
                        repo_finder_outcome=repo_finder_outcome,
                    )

                return Analyzer.AnalysisTarget(
                    parsed_purl=parsed_purl,
                    repo_path=repo_path_input,
                    branch=input_branch,
                    digest=provenance_commit_digest or "",
                    repo_finder_outcome=repo_finder_outcome,
                )

            case _:
                # Even though this case is unnecessary, it is still put here because mypy cannot type-narrow tuples
                # correctly (see https://github.com/python/mypy/pull/16905, which was fixed, but not released).
                raise InvalidAnalysisTargetError(
                    "Cannot determine the analysis target: PURL and repository path are missing."
                )

    def create_analyze_ctx(self, component: Component) -> AnalyzeContext:
        """Create and return an analysis context for the passed component.

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

    def get_artifact_hash(
        self,
        purl: PackageURL,
        local_artifact_dirs: list[str] | None,
        package_registries_info: list[PackageRegistryInfo],
    ) -> str | None:
        """Get the hash of the artifact found from the passed PURL using local or remote files.

        Provided local caches will be searched first. Artifacts will be downloaded if nothing is found within local
        caches, or if no appropriate cache is provided for the target language.
        Downloaded artifacts will be added to the passed package registry to prevent downloading them again.

        Parameters
        ----------
        purl: PackageURL
            The PURL of the artifact.
        local_artifact_dirs: list[str] | None
            The list of directories that may contain the artifact file.
        package_registries_info: list[PackageRegistryInfo]
            The list of package registry information.

        Returns
        -------
        str | None
            The hash of the artifact, or None if no artifact can be found locally or remotely.
        """
        if local_artifact_dirs:
            # Try to get the hash from a local file.
            artifact_hash = get_local_artifact_hash(purl, local_artifact_dirs)

            if artifact_hash:
                return artifact_hash

        # Download the artifact.
        if purl.type == "maven":
            maven_registry = next(
                (
                    package_registry
                    for package_registry in PACKAGE_REGISTRIES
                    if isinstance(package_registry, MavenCentralRegistry)
                ),
                None,
            )
            if not maven_registry:
                return None

            return maven_registry.get_artifact_hash(purl)

        if purl.type == "pypi":
            pypi_registry = next(
                (
                    package_registry
                    for package_registry in PACKAGE_REGISTRIES
                    if isinstance(package_registry, PyPIRegistry)
                ),
                None,
            )
            if not pypi_registry:
                logger.debug("Missing registry for PyPI")
                return None

            registry_info = next(
                (
                    info
                    for info in package_registries_info
                    if info.package_registry == pypi_registry and info.build_tool_name in {"pip", "poetry"}
                ),
                None,
            )
            if not registry_info:
                logger.debug("Missing registry information for PyPI")
                return None

            if not purl.version:
                return None

            pypi_asset = find_or_create_pypi_asset(purl.name, purl.version, registry_info)
            if not pypi_asset:
                return None

            pypi_asset.has_repository = True
            if not pypi_asset.download(""):
                return None

            artifact_hash = pypi_asset.get_sha256()
            if artifact_hash:
                return artifact_hash

            source_url = pypi_asset.get_sourcecode_url("bdist_wheel")
            if not source_url:
                return None

            return pypi_registry.get_artifact_hash(source_url)

        logger.debug("Purl type '%s' not yet supported for GitHub attestation discovery.", purl.type)
        return None

    def get_github_attestation_payload(
        self, analyze_ctx: AnalyzeContext, git_service: GitHub, artifact_hash: str
    ) -> InTotoPayload | None:
        """Get the GitHub attestation associated with the given PURL, or None if it cannot be found.

        The schema of GitHub attestation can be found on the API page:
        https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#list-attestations

        Parameters
        ----------
        analyze_ctx: AnalyzeContext
            The analysis context.
        git_service: GitHub
            The Git service to retrieve the attestation from.
        artifact_hash: str
            The hash of the related artifact.

        Returns
        -------
        InTotoPayload | None
            The attestation payload, if found.
        """
        git_attestation_dict = git_service.api_client.get_attestation(
            analyze_ctx.component.repository.full_name, artifact_hash
        )

        if not git_attestation_dict:
            return None

        git_attestation_list = json_extract(git_attestation_dict, ["attestations"], list)
        if not git_attestation_list:
            return None

        payload = decode_provenance(git_attestation_list[0])

        try:
            return validate_intoto_payload(payload)
        except ValidateInTotoPayloadError as error:
            logger.debug("Invalid attestation payload: %s", error)
            return None

    def _determine_git_service(self, analyze_ctx: AnalyzeContext) -> BaseGitService:
        """Determine the Git service used by the software component."""
        remote_path = analyze_ctx.component.repository.remote_path if analyze_ctx.component.repository else None
        git_service = get_git_service(remote_path)

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
                callgraph = ci_service.build_call_graph(analyze_ctx.component.repository.fs_path)
                analyze_ctx.dynamic_data["ci_services"].append(
                    CIInfo(
                        service=ci_service,
                        callgraph=callgraph,
                        provenance_assets=[],
                        release={},
                        provenances=[
                            SLSAProvenanceData(
                                payload=InTotoV01Payload(statement=InferredProvenance().payload),
                                asset=VirtualReleaseAsset(name="No_ASSET", url="NO_URL", size_in_bytes=0),
                            )
                        ],
                        build_info_results=InTotoV01Payload(statement=InferredProvenance().payload),
                    )
                )

    def _populate_package_registry_info(self) -> list[PackageRegistryInfo]:
        """Add all possible package registries to the analysis context."""
        package_registries = []
        for package_registry in PACKAGE_REGISTRIES:
            for build_tool in BUILD_TOOLS:
                build_tool_name = build_tool.name
                if build_tool_name not in package_registry.build_tool_names:
                    continue
                package_registries.append(
                    PackageRegistryInfo(
                        build_tool_name=build_tool_name,
                        build_tool_purl_type=build_tool.purl_type,
                        package_registry=package_registry,
                    )
                )
        return package_registries

    def _determine_package_registries(
        self, analyze_ctx: AnalyzeContext, package_registries_info: list[PackageRegistryInfo]
    ) -> None:
        """Determine the package registries used by the software component based on its build tools."""
        build_tools = (
            analyze_ctx.dynamic_data["build_spec"]["tools"] or analyze_ctx.dynamic_data["build_spec"]["purl_tools"]
        )
        build_tool_names = {build_tool.name for build_tool in build_tools}
        relevant_package_registries = []
        for package_registry in package_registries_info:
            if package_registry.build_tool_name not in build_tool_names:
                continue
            relevant_package_registries.append(package_registry)

        # Assign the updated list of registries.
        analyze_ctx.dynamic_data["package_registries"] = relevant_package_registries

    def _verify_repository_link(self, parsed_purl: PackageURL, analyze_ctx: AnalyzeContext) -> None:
        """Verify whether the claimed repository links back to the artifact."""
        if not analyze_ctx.component.repository:
            logger.debug("The repository is not available. Skipping the repository verification.")
            return

        if parsed_purl.namespace is None or parsed_purl.version is None:
            logger.debug("The PURL is not complete. Skipping the repository verification.")
            return

        build_tools = (
            analyze_ctx.dynamic_data["build_spec"]["tools"] or analyze_ctx.dynamic_data["build_spec"]["purl_tools"]
        )

        analyze_ctx.dynamic_data["repo_verification"] = []

        for build_tool in build_tools:
            verification_result = verify_repo(
                namespace=parsed_purl.namespace,
                name=parsed_purl.name,
                version=parsed_purl.version,
                reported_repo_url=analyze_ctx.component.repository.remote_path,
                reported_repo_fs=analyze_ctx.component.repository.fs_path,
                build_tool=build_tool,
            )
            analyze_ctx.dynamic_data["repo_verification"].append(verification_result)

    @staticmethod
    def _get_local_artifact_repo_mapper() -> Mapping[str, str]:
        """Return the mapping between purl type and its local artifact repo path if that path exists."""
        local_artifact_mapper: dict[str, str] = {}

        if global_config.local_maven_repo:
            m2_repository_dir = os.path.join(global_config.local_maven_repo, "repository")
            if os.path.isdir(m2_repository_dir):
                local_artifact_mapper["maven"] = m2_repository_dir

        if global_config.python_venv_path:
            site_packages_dir_pattern = os.path.join(
                global_config.python_venv_path,
                "lib",
                "python3.*",
                "site-packages",
            )
            site_packages_dirs = glob.glob(site_packages_dir_pattern)

            if len(site_packages_dirs) == 1:
                local_artifact_mapper["pypi"] = site_packages_dirs.pop()
            else:
                logger.info(
                    "There are multiple python3.* directories in the input Python venv. "
                    + "This venv will NOT be used for local artifact findings."
                )

        return local_artifact_mapper


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
