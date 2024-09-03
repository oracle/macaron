# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the InferArtifactPipelineCheck class to check if an artifact is published from a pipeline automatically."""

import logging
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.config.defaults import defaults
from macaron.database.table_definitions import CheckFacts
from macaron.errors import InvalidHTTPResponseError, ProvenanceError
from macaron.json_tools import json_extract
from macaron.repo_finder.provenance_extractor import ProvenancePredicate
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.ci_service.base_ci_service import NoneCIService
from macaron.slsa_analyzer.package_registry.maven_central_registry import MavenCentralRegistry
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


class ArtifactPipelineFacts(CheckFacts):
    """The ORM mapping for justifications of the infer_artifact_pipeline check."""

    __tablename__ = "_artifact_pipeline_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The URL of the workflow file that triggered deploy.
    deploy_workflow: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.HREF})

    #: The workflow job that triggered deploy.
    deploy_job: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The workflow step that triggered deploy.
    deploy_step: Mapped[str | None] = mapped_column(
        String, nullable=True, info={"justification": JustificationType.TEXT}
    )

    #: The workflow run URL.
    run_url: Mapped[str | None] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

    #: The triggering workflow is found from a provenance.
    from_provenance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, info={"justification": JustificationType.TEXT}
    )

    #: The CI pipeline data is deleted.
    run_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, info={"justification": JustificationType.TEXT})

    #: The artifact has been published before the code was committed to the source-code repository.
    published_before_commit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, info={"justification": JustificationType.TEXT}
    )

    __mapper_args__ = {
        "polymorphic_identity": "_infer_artifact_pipeline_check",
    }


class ArtifactPipelineCheck(BaseCheck):
    """This check detects a pipeline from which an artifact is published.

    When a verifiable provenance is found for an artifact, we use it to obtain the pipeline trigger.
    Otherwise, we use heuristics to check whether a CI workflow run has automatically published the artifact.

    We use several heuristics in this check for inference:

      * The workflow run should have started before the artifact is published.
      * The workflow step that calls a deploy command should have run successfully.
      * The workflow step that calls a deploy command should have started before the artifact is published.

    Note: due to a limitation, we cannot specify the provenance checks as parents of this
    check because a check cannot have more than one parent in the current design. It would
    be good to skip this with a success result if the relevant provenance checks pass in the future.
    """

    def __init__(self) -> None:
        """Initialize the InferArtifactPipeline instance."""
        check_id = "mcn_find_artifact_pipeline_1"
        description = """
        Detects pipelines from which an artifact is published.

        When a verifiable provenance is found for an artifact, we use it to obtain the pipeline trigger.
        """
        depends_on: list[tuple[str, CheckResultType]] = [("mcn_build_as_code_1", CheckResultType.PASSED)]
        eval_reqs: list[ReqName] = []
        super().__init__(
            check_id=check_id,
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
        )

    def run_check(self, ctx: AnalyzeContext) -> CheckResultData:
        """Implement the check in this method.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.

        Returns
        -------
        CheckResultData
            The result type of the check.
        """
        # This check requires a repository to be available.
        if not ctx.component.repository:
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        # Look for the artifact in the corresponding registry and find the publish timestamp.
        artifact_published_date = None
        package_registry_info_entries = ctx.dynamic_data["package_registries"]
        for package_registry_info_entry in package_registry_info_entries:
            match package_registry_info_entry:
                # TODO: add package registries for other ecosystems.
                case PackageRegistryInfo(
                    build_tool=Gradle() | Maven(),
                    package_registry=MavenCentralRegistry() as mvn_central_registry,
                ):
                    group_id = ctx.component.namespace
                    artifact_id = ctx.component.name
                    version = ctx.component.version
                    try:
                        artifact_published_date = mvn_central_registry.find_publish_timestamp(
                            group_id, artifact_id, version
                        )
                    except InvalidHTTPResponseError as error:
                        logger.debug(error)

        # This check requires the timestamps of published artifact and its source-code commit to proceed.
        # If the timestamps are not found, we return with a fail result.
        try:
            commit_date = datetime.strptime(ctx.component.repository.commit_date, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError as error:
            logger.debug("Failed to parse date string '%s': %s", ctx.component.repository.commit_date, error)
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        if not artifact_published_date:
            logger.debug("Unable to find a publish date for the artifact.")
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        # If an artifact is published before the corresponding code is committed, there cannot be
        # a CI pipeline that triggered the publishing.
        if published_before_commit := artifact_published_date < commit_date:
            logger.debug("Publish date %s is earlier than commit date %s.", artifact_published_date, commit_date)

        # Found an acceptable publish timestamp to proceed.
        logger.debug("Publish date %s is later than commit date %s.", artifact_published_date, commit_date)

        # If a provenance is found, obtain the workflow and the pipeline that has triggered the artifact release.
        prov_workflow = None
        prov_trigger_run = None
        prov_payload = ctx.dynamic_data["provenance"]
        if not ctx.dynamic_data["is_inferred_prov"] and prov_payload:
            # Obtain the build-related fields from the provenance.
            try:
                build_def = ProvenancePredicate.find_build_def(prov_payload.statement)
            except ProvenanceError as error:
                logger.error(error)
                return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)
            prov_workflow, prov_trigger_run = build_def.get_build_invocation(prov_payload.statement)

        # Obtain the metadata inferred by the build_as_code check, which is stored in the `provenances`
        # attribute of the corresponding CI service.
        ci_services = ctx.dynamic_data["ci_services"]
        for ci_info in ci_services:
            ci_service = ci_info["service"]
            # Checking if a CI service is discovered for this repo.
            if isinstance(ci_service, NoneCIService):
                continue

            # Different CI services have different retention policies for the workflow runs.
            # Make sure the artifact is not older than the retention date.
            ci_run_deleted = ci_service.workflow_run_deleted(artifact_published_date)

            # If the artifact is published before the source code is committed, the check should fail.
            if published_before_commit:
                return CheckResultData(
                    result_tables=[
                        ArtifactPipelineFacts(
                            from_provenance=bool(prov_workflow),
                            run_deleted=ci_run_deleted,
                            published_before_commit=published_before_commit,
                            confidence=Confidence.HIGH,
                        )
                    ],
                    result_type=CheckResultType.FAILED,
                )
            # Obtain the job and step calling the deploy command.
            # This data must have been found already by the build-as-code check.
            build_predicate = ci_info["build_info_results"].statement["predicate"]
            if build_predicate is None:
                continue
            build_entry_point = json_extract(build_predicate, ["invocation", "configSource", "entryPoint"], str)

            # If provenance exists check that the entry point extracted from the build-as-code check matches.
            if build_entry_point is None or (prov_workflow and not build_entry_point.endswith(prov_workflow)):
                continue

            if not (job_id := json_extract(build_predicate, ["buildConfig", "jobID"], str)):
                continue

            step_id = json_extract(build_predicate, ["buildConfig", "stepID"], str)
            step_name = json_extract(build_predicate, ["buildConfig", "stepName"], str)
            callee_node_type = json_extract(build_predicate, ["buildConfig", "calleeType"], str)

            try:
                publish_time_range = defaults.getint("package_registry", "publish_time_range", fallback=7200)
            except ValueError as error:
                logger.error(
                    "Configuration error: publish_time_range in section of package_registries is not a valid integer %s.",
                    error,
                )
                return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

            # Find the workflow runs that have potentially triggered the artifact publishing.
            html_urls = ci_service.workflow_run_in_date_time_range(
                repo_full_name=ctx.component.repository.full_name,
                workflow=build_entry_point,
                publish_date_time=artifact_published_date,
                commit_date_time=commit_date,
                job_id=job_id,
                step_name=step_name,
                step_id=step_id,
                time_range=publish_time_range,
                callee_node_type=callee_node_type,
            )

            # If provenance exists, we expect the timestamp of the reported triggered run
            # to be within an acceptable range, have succeeded, and called the deploy command.
            if prov_trigger_run:
                result_type = CheckResultType.FAILED
                # If the triggering run in the provenance does not satisfy any of the requirements above,
                # set the confidence as medium because the build-as-code results might be imprecise.
                confidence = Confidence.MEDIUM
                if prov_trigger_run in html_urls:
                    # The workflow's deploy step has been successful. In this case, the check can pass with a
                    # high confidence.
                    confidence = Confidence.HIGH
                    result_type = CheckResultType.PASSED
                elif ci_run_deleted:
                    # The workflow run data has been deleted and we cannot analyze any further.
                    confidence = Confidence.LOW
                    result_type = CheckResultType.UNKNOWN

                return CheckResultData(
                    result_tables=[
                        ArtifactPipelineFacts(
                            deploy_workflow=build_entry_point,
                            deploy_job=job_id,
                            deploy_step=step_id or step_name,
                            run_url=prov_trigger_run,
                            from_provenance=True,
                            run_deleted=ci_run_deleted,
                            published_before_commit=published_before_commit,
                            confidence=confidence,
                        )
                    ],
                    result_type=result_type,
                )

            # Logic for artifacts that do not have a provenance.
            result_tables: list[CheckFacts] = []
            for html_url in html_urls:
                result_tables.append(
                    ArtifactPipelineFacts(
                        deploy_workflow=build_entry_point,
                        deploy_job=job_id,
                        deploy_step=step_id or step_name,
                        run_url=html_url,
                        from_provenance=False,
                        run_deleted=ci_run_deleted,
                        published_before_commit=published_before_commit,
                        confidence=Confidence.MEDIUM,
                    )
                )
            if html_urls:
                return CheckResultData(result_tables=result_tables, result_type=CheckResultType.PASSED)
            if ci_run_deleted:
                # We set the confidence as low because the analysis could not be performed due to missing
                # CI run data.
                return CheckResultData(
                    result_tables=[
                        ArtifactPipelineFacts(
                            deploy_workflow=build_entry_point,
                            deploy_job=job_id,
                            deploy_step=step_id or step_name,
                            run_url=None,
                            from_provenance=False,
                            run_deleted=ci_run_deleted,
                            published_before_commit=published_before_commit,
                            confidence=Confidence.LOW,
                        )
                    ],
                    result_type=CheckResultType.UNKNOWN,
                )

        if ci_run_deleted or published_before_commit:
            # If the CI run data is deleted or the artifact is older than the source-code commit,
            # The check should have failed earlier and we should not reach here.
            logger.debug("Unexpected error has happened.")
            return CheckResultData(
                result_tables=[],
                result_type=CheckResultType.FAILED,
            )

        # We should reach here when the analysis has failed to detect any successful deploy step in a
        # CI run. In this case the check fails with a medium confidence.
        return CheckResultData(
            result_tables=[
                ArtifactPipelineFacts(
                    from_provenance=False,
                    run_deleted=False,
                    published_before_commit=False,
                    confidence=Confidence.MEDIUM,
                )
            ],
            result_type=CheckResultType.FAILED,
        )


registry.register(ArtifactPipelineCheck())
